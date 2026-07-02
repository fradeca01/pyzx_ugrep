"""
Universal Representation Module
-------------------------------
This module provides functionality for converting stabilizer codes into a Universal 
Graph Representation (UGR). 

"""


import itertools
import pprint
import re
import pathlib

try:
    from minizinc import Instance, Model, Solver
except Exception:
    Instance = Model = Solver = None

import time
from fractions import Fraction
from typing import List, Tuple, Dict, Generic, TypeVar, Set, cast

import stim
from pyzx.circuit import Circuit
from pyzx.utils import EdgeType, VertexType
from pyzx.graph.base import BaseGraph
from pyzx.symbolic import Poly

from .graph_states import GraphState
from pyzx.extract import connectivity_from_biadj, bi_adj

VT = TypeVar('VT', bound=int)
ET = TypeVar('ET')

__all__ = [
    "graph_state_to_ZXCF",
    "ZXCF_to_UGR",
    "implement_encoder",
    "distance_upper_bound",
    "stabilizers_to_UGR",
    "stabilizers_to_ZX_graph",
    "graph_to_ZXCF",
    "benchmark_graph_state_to_ZXCF",
    "UGR",
    "ZXCF",
    "to_distance_mzn",
    "compute_distance",
    "to_stabilizer_tableau"
]


class UGR():
    """
    Data class representing the Universal Graph Representation of a stabilizer code.
    
    Attributes
    -----------
    inputs : List[int] 
        Input vertices.
    adj : List[List[int]] 
        Adjacency list of the graph.
    pivots : List[int] 
        Vertices identified as pivots during RREF reduction.
    """

    def __init__(self, inputs : List[int], adj : List[List[int]], 
                 pivots : List[int], local_cliffords : Dict[int, str]):
        self.inputs = inputs
        self.adj = adj
        self.pivots = pivots
        self.local_cliffords = local_cliffords 


class ZXCF(Generic[VT, ET]):
    """
    Data class representing the ZX canonical form of a stabilizer code.

    Attributes
    -----------
    inputs : List[VT] 
        Input vertices.
    graph : BaseGraph[VT, ET] 
        The ZX diagram representing the code.
    pivots : List[VT]  
        Vertices identified as pivots during RREF reduction.
    """

    
    def __init__(self, graph: BaseGraph[VT, ET], inputs : List[VT],  pivots : List[VT]):
        self.inputs = inputs
        self.graph = graph
        self.pivots = pivots
        

def get_node_from_boundary(g : BaseGraph[VT, ET], v : VT) -> VT:
    """
    Get the internal node connected to a boundary vertex.

    Args:
        g (BaseGraph): A ZX diagram.
        v (VT): The vertex.

    Returns:
        VT: the state vertex corresponding to the state.

    Raises: 
        ValueError: If the vertex is not a boundary vertex 
        ValueError: If g is not well formed
    """

    if not g.is_well_formed():
        raise ValueError(f"{g} is not well formed")

    if g.type(v) != VertexType.BOUNDARY:
        raise ValueError(f"{v} is not a boundary vertex.")
    
    ns = list(g.neighbors(v))
    return ns[0]

def get_neighbors(g : BaseGraph[VT, ET], v: VT) -> List[VT]:
    """
    Get the neighbors of an iternal vertex.
    
    Args:
        g (BaseGraph): A ZX diagram.
        v (VT): The internal vertex
    
    Returns:
        List[VT]: List of neighboring internal vertices
        
    Raises:
        ValueError: If the vertex is not a state vertex.
        ValueError: If g is not well formed
    """


    if not g.is_well_formed():
        raise ValueError(f"{g} is not well formed")

    if g.type(v) == VertexType.BOUNDARY:
        raise ValueError(f"{v} is not an internal vertex.")

    neighbors = [x for x in g.neighbors(v) if g.type(x) != VertexType.BOUNDARY]

    return neighbors

def get_inputs(g : BaseGraph[VT, ET]) -> List[VT]:
    """
    Get the (non boundary) input vertices.

    Args:
        g (BaseGraph): A ZX diagram.

    Returns:
        List[VT]: The list of input vertices.

    Raises:
        ValueError: If g is not well formed
    """

    if not g.is_well_formed():
        raise ValueError(f"{g} is not well formed")

    boundary_inputs = g.inputs()   
    
    return [get_node_from_boundary(g, s) for s in boundary_inputs]

def get_outputs(g : BaseGraph[VT, ET]) -> List[VT]:
    """
    Get the (non boundary) output vertices.

    Args:
        g (BaseGraph): A ZX diagram.

    Returns:
        List[VT]: The list of output vertices.

    Raises:
        ValueError: If the graph g is not well formed.
    """

    if not g.is_well_formed():
        raise ValueError(f"{g} is not well formed")

    boundary_outputs = g.outputs()


    
    return [get_node_from_boundary(g, s) for s in boundary_outputs]
    # return [get_node_from_boundary(g, s) for s in g.outputs()]

def to_RRREF(g : BaseGraph[VT, ET], quiet : bool = True) -> List[VT]:
    """
    Transform the graph so the partial adjacency matrix between inputs and outputs is in row reduced echelon form by applying unitaries only on input vertices.

    Args:
        g (BaseGraph): A ZX diagram. 
        quiet (bool): If false display debug informations
       
    Returns:
        List[VT]: List of pivot vertices after gauss elimination.
    """
 
    inputs = get_inputs(g)
    outputs = get_outputs(g)

    mat = bi_adj(g, inputs, outputs)
    mat = mat.transpose()

    if not quiet:
        print(f"Step {7}: --- Reducing the partial adjacency matrix to RREF:")
        print(mat)
        print(">>>>>>>>>")

    mat.gauss(full_reduce=True)

    pivots = []

    for i in range(mat.rows()):
        for j in range(mat.cols()):
            if mat[i, j] != 0:
                pivots.append(j)
                break

    pivots = [outputs[j] for j in pivots]

    if not quiet:
        print(mat)
        
    mat = mat.transpose()

    connectivity_from_biadj(g, mat, inputs, outputs)

    if not quiet:
        print(f"Step {7}:  --- PIVOTS: {pivots}")    

    return pivots


def remove_unitaries_input(g : BaseGraph[VT, ET], quiet : bool = True) -> None:
    """
    Remove unitary operations from input vertices by applying unitaries only on input vertices. This is equivalent to remove phases from input spiders.

    Args:
        g (BaseGraph): A ZX diagram. 
        quiet (bool): If false display debug informations
    """
    ins = list(g.inputs())

    for s in ins:
        v = get_node_from_boundary(g, s)
        g.set_phase(v, 0)
        e = g.edge(v, s)
        g.set_edge_type(e, EdgeType.SIMPLE)

    for s1, s2 in itertools.product(ins,ins):
        v = get_node_from_boundary(g, s1)
        w = get_node_from_boundary(g, s2)
        if g.connected(v, w):
            e = g.edge(v, w)
            g.remove_edge(e)

    if not quiet:
        print(f"Step: --- Removed unitaries from inputs")

def remove_pivot_phases(g : BaseGraph[VT, ET], pivots : List[VT], quiet : bool = True) -> None:
    """
    Eliminates phases on pivot vertices via local complementation.
    
    Args:
        g (BaseGraph): A ZX diagram. 
        pivots (List[VT]): List of pivot vertices.
        quiet (bool): If false display debug informations.
    """

    if not quiet:
        print(f"Step {8}: --- Removing pivot phases for pivots: {pivots}")

    go_on = True
    while go_on:
        go_on = False
        for v in pivots:
            if g.phase(v) != 0:
                inputs_states = get_inputs(g)
                outputs_states = get_outputs(g)

                vin = None

                for x in get_neighbors(g, v):
                    if x in inputs_states:
                        vin = x
                        break

                if vin is None:
                    raise ValueError(f"Pivot vertex {v} is not connected to an input vertex")

                neighborsin = [x for x in get_neighbors(g, vin) if x in outputs_states]

                for x, y in itertools.combinations(neighborsin, 2):
                    if g.connected(x, y):
                        g.remove_edge(g.edge(x, y))
                    else:
                        g.add_edge((x, y), edgetype=EdgeType.HADAMARD)

                for x in neighborsin:
                    g.add_to_phase(x, Fraction(1, 2))

                g.set_phase(vin, 0)

                go_on = True
                break

def remove_pivot_edges(g : BaseGraph[VT, ET], pivots : List[VT], quiet : bool = True) -> None:
    """
    Remove edges between pivot vertices.
    
    Args:
        pivots: List of pivot vertices
    """

    inputs = set(get_inputs(g))
    outputs = set(get_outputs(g))

    def toggle_edge(x: VT, y: VT) -> None:
        if x == y:
            g.add_to_phase(x, 1)
        elif g.connected(x, y):
            g.remove_edge(g.edge(x, y))
        else:
            g.add_edge((x, y), edgetype=EdgeType.HADAMARD)

    def pivot_to_input() -> Dict[VT, VT]:
        matching: Dict[VT, VT] = {}
        for pivot in pivots:
            input_neighbors = [v for v in get_neighbors(g, pivot) if v in inputs]
            if len(input_neighbors) != 1:
                raise ValueError(
                    f"Pivot vertex {pivot} should be connected to exactly one input, "
                    f"got {input_neighbors}"
                )
            matching[pivot] = input_neighbors[0]
        return matching

    def add_input_row(source: VT, target: VT) -> None:
        for output in list(get_neighbors(g, source)):
            if output in outputs:
                toggle_edge(target, output)

    def swap_input_rows(x: VT, y: VT) -> None:
        add_input_row(x, y)
        add_input_row(y, x)
        add_input_row(x, y)

    def pivot(x: VT, y: VT) -> None:
        if not g.connected(x, y):
            g.add_edge((x, y), edgetype=EdgeType.HADAMARD)

        nx = set(get_neighbors(g, x))
        ny = set(get_neighbors(g, y))
        nx.add(x)
        ny.add(y)

        for v in (nx & ny) - {x, y}:
            g.add_to_phase(v, 1)

        for a in nx:
            for b in ny:
                if a == b:
                    continue
                toggle_edge(a, b)

        if g.connected(x, y):
            g.remove_edge(g.edge(x, y))

    while True:
        pivot_edges = [
            (x, y)
            for x, y in itertools.combinations(pivots, 2)
            if g.connected(x, y)
        ]

        if not pivot_edges:
            return

        before = len(pivot_edges)
        matching = pivot_to_input()
        x, y = pivot_edges[0]

        if not quiet:
            print(f"Step {9}:  --- Removing pivot-pivot edge ({x}, {y})")

        pivot(matching[x], matching[y])
        swap_input_rows(matching[x], matching[y])

        after = sum(
            1
            for a, b in itertools.combinations(pivots, 2)
            if g.connected(a, b)
        )

        if after >= before:
            raise ValueError(
                "Pivot-edge removal did not reduce the number of pivot-pivot edges"
            )


def stabilizers_to_UGR(code : List[str]) -> UGR:
    """Convert a stabilizer code to its uinversal graph representation.

    Args:
        g (GraphState): The GraphState to convert.
        inputs (list[VT]): List of input vertices

    Returns:
        ZXCF: The ZX canonical form.
    """

    zx_graph = stabilizers_to_ZX_graph(code)
    zxcf = graph_to_ZXCF(zx_graph)
    ugr = ZXCF_to_UGR(zxcf)
    return ugr

def graph_state_to_ZXCF(g: GraphState[VT, ET], inputs : List[VT]) -> ZXCF:
    """Convert a GraphState to its uinversal representation.

    Args:
        code (List[str]): A list of stabilizers.

    Returns:
        UGR: The universal graph representation.
    """
    if not g.validate_canonical_form():
        g.to_canonical_form(quiet=True)
    g2 = state_to_map(g, inputs)
    remove_unitaries_input(g2)
    pivots = to_RRREF(g2, quiet = True)
    remove_pivot_phases(g2, pivots, quiet = True)
    remove_pivot_edges(g2, pivots, quiet = True)
    remove_unitaries_input(g2)
    pivots = to_RRREF(g2, quiet = True)

    return ZXCF(g2, inputs, pivots)

def benchmark_graph_state_to_ZXCF(g: GraphState[VT, ET]) -> Tuple[float, float, float, float]:

    g.to_canonical_form(quiet=True)
    g2 = g.state_to_map()

    start = time.perf_counter()
    pivots = to_RRREF(g2, quiet = True)
    end1 = time.perf_counter()
    remove_pivot_phases(g2, pivots, quiet = True)
    end2 = time.perf_counter()
    remove_pivot_edges(g2, pivots, quiet = True)
    end3 = time.perf_counter()
    remove_unitaries_input(g2)
    end4 = time.perf_counter()

    time_rref = end1 - start
    time_remove_phases = end2 - end1
    time_remove_edges = end3 - end2
    time_remove_unitaries = end4 - end3
    return time_rref, time_remove_phases, time_remove_edges, time_remove_unitaries

def ZXCF_to_UGR(g: ZXCF[VT, ET], quiet : bool = True) -> UGR:
    """
    
    Convert a ZX diagram canonical form to its universal graph representation.

    Args:
        g (ZXCF) : The ZX canonical form diagram.
        quiet (bool) : If false display debug informations.

    Returns:
        UGR: The correspondent universal graph representation.
    """
    g2 = g.graph.clone()

    internal_inputs = get_inputs(g2)
    internal_outputs = get_outputs(g2)

    for v in g2.vertex_set():
        if g2.type(v) == VertexType.BOUNDARY:
            g2.remove_vertex(v)

    g2.set_inputs(tuple(internal_inputs))
    g2.set_outputs(tuple(internal_outputs))

    d = g2.to_dict()

    vertex_map = {}
    adjacency_list = [[] for _ in range(len(d["vertices"]))]

    for i in range(len(internal_inputs)):
        vertex_map[internal_inputs[i]] = i

    for i in range(len(internal_inputs), len(internal_outputs) + len(internal_inputs)):
        vertex_map[internal_outputs[i - len(internal_inputs)]] = i

    for e in d["edges"]:
        v1 = vertex_map[e[0]]
        v2 = vertex_map[e[1]]

        adjacency_list[v1].append(v2)
        adjacency_list[v2].append(v1)

    local_cliffords = {vertex_map[v] : "" for v in internal_outputs}

    for v in internal_outputs:
        phase = g2.phase(v)
        if phase == Fraction(1,2):
            local_cliffords[vertex_map[v]] += "S"
        elif phase == 1:
            local_cliffords[vertex_map[v]] += "Z"
        elif phase == Fraction(3,2):
            local_cliffords[vertex_map[v]] += "SZ"

    for b in g.graph.outputs():
        v = get_node_from_boundary(g.graph, b)
        if g.graph.edge_type(g.graph.edge(v, b)) == EdgeType.HADAMARD:
            local_cliffords[vertex_map[v]] = "H" + local_cliffords[vertex_map[v]]
    

    new_inputs =[vertex_map[x] for x in  d["inputs"]]

    pivots = [vertex_map[x] for x in g.pivots]

    export = UGR(new_inputs, adjacency_list, pivots, local_cliffords)
    return export


def state_to_map(g : GraphState[VT, ET], inputs : List[VT]) -> BaseGraph[VT, ET]:
    """
    Export graph state to a ZX-diagram.

    Args:
        g (GraphState) : A GraphState ZX diagram.
        inputs (List[VT]) : List of vertices of the graph state that should become inputs.

    Returns:
        BaseGraph: The ZX diagram which is the graph state after converting output vertices to input vertices.

    """

    export_g = g.get_graph().clone()
    outputs = [i for i in g.outputs() if i not in inputs]
    export_g.set_inputs(tuple(inputs))
    export_g.set_outputs(tuple(outputs))        
  
    export_g.normalize()

    return export_g


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


def stabilizers_to_ZX_graph(code : List[str]) -> BaseGraph:
    """
    Given a list of stabilizer for a code, return a ZX diagram that correspond to an encoder for the code. The encoder is in extended graph state form.

    Args:
        code (List[str]): A list of stabilizers.

    Returns:
        BaseGraph: A ZX diagram.
    """

    def stim_qasm_comply(qasm: str) -> str:
        q = qasm
        q = re.sub(r'def\s+rx\(qubit q0\)\s*\{[^}]*\}\n+', '', q)
        q = re.sub(r'rx\s*\(\s*q\[(\d+)\]\s*\)\s*;', r'h q[\1];', q)
        q = re.sub(r'reset\s+q\[(\d+)\];', '', q)
        return q

    code2 = [stim.PauliString(x) for x in code]
    # print(code2)
    n = len(code2[0])
    k = n - len(code2)

    # print(n, k)
    tableau = stim.Tableau.from_stabilizers(code2, allow_underconstrained=True)

    stabilizers = []

    for i in range(k, n):
        stabilizers.append(stim.PauliString(f"Z{i}") * stim.PauliString(n+k))


    for i in range(k):
        stabilizers.append(stim.PauliString(f"Z{i}*Z{i+n}") * stim.PauliString(n+k)) 
        stabilizers.append(stim.PauliString(f"X{i}*X{i+n}") * stim.PauliString(n+k)) 

    state = stim.TableauSimulator()
    state.set_state_from_stabilizers(stabilizers)
    state.do_tableau(tableau, list(range(k,n+k)))
    t = state.current_inverse_tableau().inverse()

    qasm_random2 = t.to_circuit(method="graph_state").to_qasm(open_qasm_version=3)       
    pyzx_circ2 = Circuit.from_qasm(stim_qasm_comply(qasm_random2))
    g2 = pyzx_circ2.to_graph()
    input_state = "0"*(n+k)
    g2.apply_state(input_state)

    g2.set_inputs(g2.outputs()[0:k])
    # d = graph_to_universal_graph_representation(g2)
    # return d
    return g2
    

def graph_to_ZXCF(g: BaseGraph[VT, ET]) -> ZXCF:
    """
    Convert a Clifford ZX diagram to its ZX canonical form.

    Args:
        g : The Clifford ZX diagram as a BaseGraph.

    Returns:
        BaseGraph: The universal representation of the GraphState.
    """
    inputs = list(g.inputs())
    g2 = GraphState(g)
    return graph_state_to_ZXCF(g2, inputs)

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

def generate_random_UGR(n : int, k : int) -> UGR:
    tableau = stim.Tableau.random(n)

    stabs = [str(stabilizer) for stabilizer in tableau.to_stabilizers()[0 : n - k]]

    return stabilizers_to_UGR(stabs)

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
        from minizinc import Instance, Model, Solver

        num_nodes = len(adjacency_list)
        I_nodes = {i + 1 for i in inputs}
        all_nodes = set(range(1, num_nodes + 1))
        O_P_nodes = all_nodes - I_nodes
        
        adj = [[False for _ in range(num_nodes)] for _ in range(num_nodes)]
        for i, neighbors in enumerate(adjacency_list):
            for neighbor in neighbors:
                adj[i][neighbor] = True
                adj[neighbor][i] = True
                
        initial_lights = [0] * (num_nodes + 1) 

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
  
