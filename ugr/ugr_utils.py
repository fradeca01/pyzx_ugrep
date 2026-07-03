import pathlib
from typing import Dict, List

import stim
from pyzx.circuit import Circuit

from .universal_representation import UGR, stabilizers_to_UGR

try:
    from minizinc import Instance, Model, Solver
except Exception:
    Instance = Model = Solver = None

__all__ = [
    "generate_random_UGR",
    "known_code",
    "known_code_stabilizers",
    "shor_code",
    "steane_code",
    "five_qubit_code",
    "five_wubit_code",
    "to_stabilizer_tableau",
    "to_distance_mzn",
    "compute_distance",
    "implement_encoder",
    "distance_upper_bound",
]

_KNOWN_CODE_STABILIZERS: Dict[str, List[str]] = {
    "steane": [
        "IIIXXXX",
        "IXXIIXX",
        "XIXIXIX",
        "IIIZZZZ",
        "IZZIIZZ",
        "ZIZIZIZ",
    ],
    "five_qubit": [
        "XZZXI",
        "IXZZX",
        "XIXZZ",
        "ZXIXZ",
    ],
    "5_qubit": [
        "XZZXI",
        "IXZZX",
        "XIXZZ",
        "ZXIXZ",
    ],
    "shor": [
        "ZZIIIIIII",
        "IZZIIIIII",
        "IIIZZIIII",
        "IIIIZZIII",
        "IIIIIIZZI",
        "IIIIIIIZZ",
        "XXXXXXIII",
        "IIIXXXXXX",
    ],
}


def generate_random_UGR(n : int, k : int) -> UGR:
    tableau = stim.Tableau.random(n)

    stabs = [str(stabilizer) for stabilizer in tableau.to_stabilizers()[0 : n - k]]

    return stabilizers_to_UGR(stabs)


def known_code_stabilizers(name: str) -> List[str]:
    key = name.lower().replace("-", "_").replace(" ", "_")
    if key not in _KNOWN_CODE_STABILIZERS:
        known = ", ".join(sorted(_KNOWN_CODE_STABILIZERS))
        raise ValueError(f"Unknown code '{name}'. Known codes: {known}")
    return list(_KNOWN_CODE_STABILIZERS[key])


def known_code(name: str) -> UGR:
    return stabilizers_to_UGR(known_code_stabilizers(name))


def shor_code() -> UGR:
    return known_code("shor")


def steane_code() -> UGR:
    return known_code("steane")


def five_qubit_code() -> UGR:
    return known_code("five_qubit")


def five_wubit_code() -> UGR:
    return five_qubit_code()



def to_stabilizer_tableau (d : UGR, quiet : bool = True) -> List[str]:
    """
    Convert a graph to a stabilizer tableau.
    
    Returns:
        A list of stabilizers representing the graph state
    """

    inputs = d.inputs
    adj = d.adj
    pivots = d.pivots
    outputs_no_pivots = list(set(range(len(adj))) - set(pivots) - set(inputs))

    out_to_in = {i : set() for i in range(len(adj)) if i not in inputs}


    for o in range(len(adj)):
        if o not in inputs:
            for x in adj[o]:
                if x in inputs:
                    out_to_in[o].add(x)


    n = len(adj) - len(inputs)
    k = len(inputs)

    pivot_for_input = dict(zip(inputs, pivots))


    stabilizers = [stim.PauliString("I"*n) for _ in range(n-k)]

    s = 0
    for i in outputs_no_pivots:
        stabilizers[s] *= stim.PauliString(f"X{i - k}")
        for j in adj[i]:
            if j not in inputs:
                stabilizers[s] *= stim.PauliString(f"Z{j-k}")

        inp = out_to_in[i]
        for a in inp:
            p = pivot_for_input[a]
            stabilizers[s] *= stim.PauliString(f"X{p-k}")

            for q in adj[p]:
                if q not in inputs:
                    stabilizers[s] *= stim.PauliString(f"Z{q-k}")

        s += 1



    stabilizers = [str(x) for x in stabilizers]

    def apply_gate_to_pauli(pauli: str, gate: str) -> tuple[int, str]:
        if gate == "H":
            if pauli == "X":
                return 1, "Z"
            if pauli == "Y":
                return -1, "Y"
            if pauli == "Z":
                return 1, "X"
        elif gate == "S":
            if pauli == "X":
                return 1, "Y"
            if pauli == "Y":
                return -1, "X"
            if pauli == "Z":
                return 1, "Z"
        elif gate == "Z":
            if pauli == "X":
                return -1, "X"
            if pauli == "Y":
                return -1, "Y"
            if pauli == "Z":
                return 1, "Z"

        return 1, pauli

    def apply_local_clifford(stabilizer: str, qubit: int, local_clifford: str) -> str:
        sign = 1 if stabilizer[0] == "+" else -1
        paulis = list(stabilizer[1:])
        has_hadamard_boundary = local_clifford.startswith("H")
        phase_label = local_clifford[1:] if has_hadamard_boundary else local_clifford

        gates = []
        if phase_label == "S":
            gates.append("S")
        elif phase_label == "Z":
            gates.append("Z")
        elif phase_label == "SZ":
            gates.extend(["S", "Z"])
        elif phase_label != "":
            raise ValueError(f"Unsupported local Clifford label: {local_clifford}")

        if has_hadamard_boundary:
            gates.append("H")

        for gate in gates:
            phase, paulis[qubit] = apply_gate_to_pauli(paulis[qubit], gate)
            sign *= phase

        return ("+" if sign == 1 else "-") + "".join(paulis)

    for output in sorted(set(range(len(adj))) - set(inputs)):
        local_clifford = d.local_cliffords.get(output, "")
        if local_clifford == "":
            continue
        stabilizers = [
            apply_local_clifford(stabilizer, output - k, local_clifford)
            for stabilizer in stabilizers
        ]
    return stabilizers

def to_distance_mzn(inputs, adj) -> str:
    dzn = ""

    # inputs = d["inputs"]
    dzn += f"I_nodes = {{{', '.join(str(x+1) for x in inputs)}}};\n"
    dzn += f"O_P_nodes = {{{', '.join(str(x+1) for x in range(len(adj)) if x not in inputs)}}};\n"

    dzn += f"adj = [|"

    for i in range(len(adj)):
        row = ""
        for j in range(len(adj)):
            if j in adj[i]:
                row += "true, "
            else:
                row += "false, "
        dzn += row[:-2] + "|\n"

    dzn += "|];\n"

    dzn += "initial_lights = array1d(O_P_nodes, ["
    for i in range(len(adj)):
        if i not in inputs:
            row = "0, "
            dzn += row
    dzn += "]);\n"

    return dzn


def compute_distance(inputs : List[int], adjacency_list : List[List[int]]) -> int:   
    num_nodes = len(adjacency_list)
    I_nodes = {i + 1 for i in inputs}
    all_nodes = set(range(1, num_nodes + 1))
    O_P_nodes = all_nodes - I_nodes
    
    adj = [[False for _ in range(num_nodes)] for _ in range(num_nodes)]
    for i, neighbors in enumerate(adjacency_list):
        for neighbor in neighbors:
            adj[i][neighbor] = True
            adj[neighbor][i] = True

    try:
        if Model is None or Solver is None or Instance is None:
            raise ImportError("MiniZinc is not available; install a working MiniZinc CLI to compute distance.")
        current_dir = pathlib.Path(__file__).parent.resolve()
        mzn_path = current_dir / "qlo.mzn"
        model = Model(str(mzn_path)) 
        solver = Solver.lookup("gecode")
        instance = Instance(solver, model)

        instance["I_nodes"] = I_nodes
        instance["O_P_nodes"] = O_P_nodes
        instance["adj"] = adj
        instance["initial_lights"] = [0] * len(O_P_nodes) 


        print("Starting MiniZinc solver...")
        result = instance.solve()

        if result:
            min_weight = result["objective"]
            return min_weight
        else:
            return -1
    except Exception as e:
        # print("EXPE")
        raise e
        
def implement_encoder(d : UGR) -> Circuit:

    inputs = d.inputs
    adj = d.adj
    pivots = d.pivots
    k = len(inputs)
    num_qubits = len(adj) - k

    if len(pivots) != k:
        raise ValueError(f"Expected one pivot per input, got {len(pivots)} pivots for {k} inputs")

    input_set = set(inputs)
    pivot_set = set(pivots)
    output_set = set(range(len(adj))) - input_set
    pivot_for_input = dict(zip(inputs, pivots))
    input_qubit = {input_vertex: i for i, input_vertex in enumerate(inputs)}
    pivot_qubit = {
        pivot: input_qubit[input_vertex]
        for input_vertex, pivot in pivot_for_input.items()
    }
    non_pivot_outputs = [
        output for output in range(len(adj))
        if output in output_set and output not in pivot_set
    ]
    output_qubit = {
        output: k + i
        for i, output in enumerate(non_pivot_outputs)
    }
    output_qubit.update(pivot_qubit)

    if any(pivot in input_set for pivot in pivots):
        raise ValueError("Pivots must be output vertices, not input vertices")

    if any(pivot not in output_set for pivot in pivots):
        raise ValueError("Pivots must be valid output vertices")

    for input_vertex, pivot in pivot_for_input.items():
        if pivot not in adj[input_vertex]:
            raise ValueError("Input is not connected to its corresponding pivot")

    c = Circuit(num_qubits)

    def to_qubit(x):
        if x in input_set:
            return input_qubit[x]
        return output_qubit[x]

    def apply_local_clifford(v: int) -> None:
        q = to_qubit(v)
        local_clifford = d.local_cliffords.get(v, "")
        has_hadamard_boundary = local_clifford.startswith("H")
        phase_label = local_clifford[1:] if has_hadamard_boundary else local_clifford

        if phase_label == "S":
            c.add_gate("S", q)
        elif phase_label == "Z":
            c.add_gate("Z", q)
        elif phase_label == "SZ":
            c.add_gate("S", q)
            c.add_gate("Z", q)
        elif phase_label != "":
            raise ValueError(f"Unsupported local Clifford label: {local_clifford}")

        if has_hadamard_boundary:
            c.add_gate("H", q)

    for v in range(len(adj)):
        if v not in pivot_set and v not in input_set:
            c.add_gate("H", to_qubit(v))

    for i in inputs:
        for j in adj[i]:
            if j not in input_set and j not in pivot_set:
                c.add_gate("CZ", to_qubit(i), to_qubit(j))
        
    for i in inputs:
        c.add_gate("H", to_qubit(i))

    for v in range(len(adj)):
        if v not in input_set:
            for u in adj[v]:
                if u not in input_set and u < v:
                    c.add_gate("CZ", to_qubit(u), to_qubit(v))

    for v in range(len(adj)):
        if v in input_set:
            continue
        apply_local_clifford(v)

    return c

def distance_upper_bound(d: UGR) -> int:
    """
    Compute an upper bound on the distance of the code represented by the graph state.

    Args:
        d (UGR): A universal graph representation.

    Returns:
        int: The upper bound on the distance of the stabilizer codes relative to this UGR.
    """

    adj = d.adj
    inp = d.inputs    

    mindeg = len(adj)

    for i in inp:
        deg = len(adj[i])
        mindeg = min(mindeg, deg) 

        for v in adj[i]:
            deg2 = len(adj[v])
            mindeg = min(mindeg, deg2)

    return mindeg
