"""
Universal representation module
"""


__all__ = [
"to_universal_representation", "implement_encoder", "from_graph_state", "benchmark_from_graph_state", "to_universal_graph_representation", "distance_upper_bound", "from_tableau"
]



from pyzx.symbolic import Poly
from .graph_states import GraphState
from .simplify import is_graph_like, spider_simp, id_simp, clifford_simp
from fractions import Fraction
from .drawing import draw_d3, draw, draw_matplotlib
from .graph.base import ET, VT, BaseGraph, EdgeType, VertexType
from .graph import Graph
from .extract import connectivity_from_biadj, bi_adj
from typing import List, Tuple, Dict, Generic, cast
import itertools
from .circuit import Circuit
import pprint
from .linalg import Mat2
import time
import stim
import re




def get_node_from_boundary(g : BaseGraph, v : VT) -> VT:
    """
    Get the internal node connected to a boundary vertex.

    Args:
        g (BaseGraph): The graph.
        v (VT): The vertex.

    Returns:
        int: the state vertex corresponding to the state.
    """

    ns = list(g.neighbors(v))

    return ns[0]

def get_neighbors(g, v: VT) -> List[VT]:
    """
    Get the neighbors of an iternal vertex.
    
    Args:
        v: The internal vertex
    
    Returns:
        List of neighboring internal vertices
        
    Raises:
        ValueError: If the vertex is not a state vertex
    """
    

    neighbors = [x for x in g.neighbors(v) if g.type(x) != VertexType.BOUNDARY]

    return neighbors

def get_internal_inputs(g) -> List[VT]:
    """
    Get the internal input vertices.

    Returns:
        List[int]: The list of input vertices.
    """
    return [get_node_from_boundary(g, s) for s in g.inputs()]

def get_internal_outputs(g) -> List[VT]:
    """
    Get the internal output vertices.

    Returns:
        List[int]: The list of output vertices.
    """
    return [get_node_from_boundary(g, s) for s in g.outputs()]

def to_RRREF(g : BaseGraph, quiet : bool = True) -> List[VT]:
    """
    Transform the graph to a reduced row echelon form.
    
    Returns:
        List of pivot vertices after gauss elimination
    """
    inputs = get_internal_inputs(g)
    outputs = get_internal_outputs(g)

    mat = bi_adj(g, inputs, outputs)
    mat = mat.transpose()

    if not quiet:
        print(f"Step {7}: --- Reducing the matrix to RREF:")
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


def remove_unitaries_input(g : BaseGraph, quiet : bool = True) -> None:
    """
    Remove unitary operations from input vertices.
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

def remove_pivot_phases(g, pivots, quiet : bool = True) -> None:
    """
    Remove local complementation pivot operations.
    
    Args:
        pivots: List of pivot vertices
    """


    if not quiet:
        print(f"Step {8}: --- Removing pivot phases for pivots: {pivots}")

    go_on = True
    while go_on:
        go_on = False
        for v in pivots:
            if g.phase(v) != 0:
                neighbors = get_neighbors(g, v)
                inputs_states = get_internal_inputs(g)
                outputs_states = get_internal_outputs(g)

                vin = -1

                for x in neighbors:
                    if x in inputs_states:
                        vin = x

                # self.get_graph().set_phase(vin, 0)

                neighborsin = [x for x in get_neighbors(g, vin) if x in outputs_states]

                for x in neighborsin:
                    g.add_to_phase(x, Fraction(1, 2))

                g.set_phase(vin, 0)

                go_on = True
                break

def pivot(g, x: VT, y: VT, quiet : bool = True, step : int = 0) -> None:
    """
    Perform a pivot operation between vertices x and y in the graph state.
    
    Args:
        x: First vertex for pivot operation
        y: Second vertex for pivot operation
        
    Raises:
        ValueError: If the graph is not in a valid state for pivoting
    """

    if not quiet:
        print(f"Step --- Pivoting between vertices {x} and {y}")

    A = get_neighbors(g,x) + [x]
    B = get_neighbors(g,y) + [y]

    phase_x = g.phase(x)
    phase_y = g.phase(y)
    # type_x = self.bound_edge_type(x)
    # type_y = self.bound_edge_type(y)

    for v in A:
        if v in B:
            if v != x and v != y:
                if not quiet:
                    print(f"Step  --- Adding phase 1 to vertex {v} in intersection of A and B")
                g.add_to_phase(v, 1)

    # Add/remove edges between A and B sets
    for i in range(len(A)):
        for j in range(len(B)):
            if A[i] == B[j]:
                continue
            elif not g.connected(A[i], B[j]):
                g.add_edge((A[i], B[j]), edgetype=EdgeType.HADAMARD)
            else:
                g.remove_edge(g.edge(A[i], B[j]))



def remove_pivot_edges(g, pivots, quiet : bool = True) -> None:
    """
    Remove edges between pivot vertices.
    
    Args:
        pivots: List of pivot vertices
    """

    for x in pivots:
        for y in pivots:
            if x != y and g.connected(x, y):
                if not quiet:
                    print(f"Step {9}:  --- Removing pivot-pivot edges from pivots: {pivots}")
                pivot(g, x, y, quiet = quiet, step=9)


def from_graph_state(g: GraphState, inputs) -> BaseGraph:
    """Convert a GraphState to its uinversal representation.

    Args:
        g (GraphState): The GraphState to convert.
        inputs: List of input vertices
        outputs: List of output vertices

    Returns:
        BaseGraph: The converted BaseGraph.
    """
    g.to_canonical_form(quiet=True)
    # draw(g, labels=True)
    print(inputs)
    state_to_map(g, inputs)
    # draw(g, labels=True)
    # print("Exporting to universal circuit...")
    remove_unitaries_input(g)
    # draw(g, labels=True)
    # print("to RRREF...")
    pivots = to_RRREF(g, quiet = True)
    # draw(g, labels=True)
    # print("Removing pivot phases...")
    remove_pivot_phases(g, pivots, quiet = True)
    # draw(g, labels=True)
    # print("Removing pivot edges...")
    remove_pivot_edges(g, pivots, quiet = True)
    # draw(g, labels=True)
    # print("Removing unitaries from inputs...")
    remove_unitaries_input(g)
    # draw(g, labels=True)

    # draw(g, labels=True)

    return g

def benchmark_from_graph_state(g: GraphState) -> Tuple[float, float, float]:

    g.to_canonical_form(quiet=True)
    g = g.state_to_map()

    start = time.perf_counter()
    pivots = to_RRREF(g, quiet = True)
    end1 = time.perf_counter()
    remove_pivot_phases(g, pivots, quiet = True)
    end2 = time.perf_counter()
    remove_pivot_edges(g, pivots, quiet = True)
    end3 = time.perf_counter()
    remove_unitaries_input(g)
    end4 = time.perf_counter()

    time_rref = end1 - start
    time_remove_phases = end2 - end1
    time_remove_edges = end3 - end2
    time_remove_unitaries = end4 - end3
    return time_rref, time_remove_phases, time_remove_edges, time_remove_unitaries

def to_universal_graph_representation(g: BaseGraph, inputs, quiet : bool = True) -> Dict:
    """
    
    Convert a Clifford ZX diagram to its universal representation.

    Args:
        g : The Clifford ZX diagram as a BaseGraph.
        inputs : List of input vertices
        quiet : If True, suppresses output messages.

    Returns:
        BaseGraph: The adjacency matrix of the universal representation.
    """
    g = to_universal_representation(g, inputs)
    d = g.to_dict()

    inputs = get_internal_inputs(g)
    outputs = get_internal_outputs(g)

    d["inputs"] = inputs
    d["outputs"] = outputs

    g_filtered = d

    # 1. collect IDs of boundary vertices
    boundary_ids = {v["id"] for v in d["vertices"] if v["t"] == VertexType.BOUNDARY}

    # 2. filter vertices
    g_filtered["vertices"] = [v for v in d["vertices"] if v["id"] not in boundary_ids]

    # 3. filter edges (remove any edge touching a boundary vertex)
    g_filtered["edges"] = [e for e in d["edges"] if e[0] not in boundary_ids and e[1] not in boundary_ids]
    # pprint.pprint(g_filtered)

    vertex_map = {}
    adjacency_list = [[] for _ in range(len(d["vertices"]))]


    # print(inputs)
    # print(outputs)


    for i in range(len(inputs)):
        vertex_map[inputs[i]] = i

    # outputs = [v for v in d["vertices"] if v["id"] not in inputs]

    for i in range(len(inputs), len(outputs) + len(inputs)):
        vertex_map[outputs[i - len(inputs)]] = i

    for e in d["edges"]:
        v1 = vertex_map[e[0]]
        v2 = vertex_map[e[1]]

        adjacency_list[v1].append(v2)
        adjacency_list[v2].append(v1)

    inp =[vertex_map[x] for x in  d["inputs"]]
    # print(g_filtered["edges"])
    return {"inputs" : inp, "adjacency_list" : adjacency_list}

def state_to_map(g, inputs) -> BaseGraph[VT, ET]:
    """
    Export graph state to a ZX-diagram.
    """
    outputs = [i for i in g.outputs() if i not in inputs]
    g.set_inputs(inputs)
    g.set_outputs(outputs)
    g.normalize()


def distance_upper_bound(d: Dict) -> int:
    """
    Compute an upper bound on the distance of the code represented by the graph state.

    Args:
        g (BaseGraph): The graph state.

    Returns:
        int: The upper bound on the distance.
    """

    adj = d["adjacency_list"]
    inp = d["inputs"]    

    mindeg = len(adj)

    for i in inp:
        deg = len(adj[i])
        mindeg = min(mindeg, deg) 

        for v in adj[i]:
            deg2 = len(adj[v])
            mindeg = min(mindeg, deg2)

    return mindeg

def stim_qasm_comply(qasm: str) -> str:
    q = qasm
    q = re.sub(r'def\s+rx\(qubit q0\)\s*\{[^}]*\}\n+', '', q)
    q = re.sub(r'rx\s*\(\s*q\[(\d+)\]\s*\)\s*;', r'h q[\1];', q)
    q = re.sub(r'reset\s+q\[(\d+)\];', '', q)
    return q

def from_tableau(code, n, k):

    code = [stim.PauliString(x) for x in code]


    tableau = stim.Tableau.from_stabilizers(code, allow_underconstrained=True)

    stabilizers = []

    for i in range (n - k):
        stabilizers.append(stim.PauliString(f"Z{i}") * stim.PauliString(n+k))

    for i in range(n-k, n): 
        stabilizers.append(stim.PauliString(f"Z{i}*Z{i+k}") * stim.PauliString(n+k)) 
        stabilizers.append(stim.PauliString(f"X{i}*X{i+k}") * stim.PauliString(n+k)) 

    state = stim.TableauSimulator()
    # print(stabilizers)
    state.set_state_from_stabilizers(stabilizers)
    state.do_tableau(tableau, range(n))
    t = state.current_inverse_tableau().inverse()

    # print("YEE2")

    qasm_random2 = t.to_circuit(method="graph_state").to_qasm(open_qasm_version=3)       
    pyzx_circ2 = Circuit.from_qasm(stim_qasm_comply(qasm_random2))
    g2 = pyzx_circ2.to_graph()
    input_state = "0"*(n+k)
    inputs = g2.outputs()[n:n+k]
    g2.apply_state(input_state)
    d = to_universal_graph_representation(g2, inputs)
    return d




def to_universal_representation(g: BaseGraph, inputs) -> BaseGraph:
    """Convert a Clifford ZX diagram to its universal representation.

    Args:
        g : The Clifford ZX diagram as a BaseGraph.

    Returns:
        BaseGraph: The universal representation of the GraphState.
    """
    g = GraphState(g)
    # draw(g, labels=True)
    return from_graph_state(g, inputs)

class Pauli:

    # (a,b,c) represents i^a * X^b * Z^c
    def __init__ (self, a, b, c):
        self.a = a % 4
        self.b = b % 2
        self.c = c % 2

    def __mul__(self, other):
        s = (self.b * other.c - self.c * other.b) % 2 # commutation factor
        a = (self.a + other.a + 2*s) % 4 # phase
        b = (self.b + other.b) % 2 # X part
        c = (self.c + other.c) % 2 # Z part
        return GraphState.Pauli(a, b, c)

    def __repr__(self):
        phase = [1, 1j, -1, -1j][self.a]
        label = { (0,0):"I", (1,0):"X", (0,1):"Z", (1,1):"Y" }[(self.b,self.c)]
        return f"{phase}*{label}"



def implement_encoder(d : Dict) -> Circuit:

    inputs = d["inputs"]
    adj = d["adjacency_list"]

    pivots = {i : -1 for i in inputs}

    out_to_in = {i : -1 for i in range(len(adj)) if i not in inputs}

    # print(inputs)
    # print(adj)

    for i in range(len(adj)):
        if i not in inputs:
            # print()
            neigh = adj[i]
            count = 0
            input = -1
            for n in neigh:
                if n in inputs:
                    count += 1
                    input = n
                    # print(n)
                    out_to_in[i] = n
            if count == 1:
                if pivots[input] == -1:
                    pivots[input] = i 

    
    n = len(adj)
    k = len(inputs)

    # print(inputs)

    c = Circuit(n)

    c.add_gate("H", n-1)
    for i in range(n-2, k-1, -1):
        c.add_gate("CNOT", n-1, i)
    
    for i in inputs:
        for j in adj[i]:
            if j not in pivots.values():
                c.add_gate("CZ", i, j)
        
    for i in inputs:
        c.add_gate("H", i)

    for v in range(n):
        if v not in inputs:
            for u in adj[v]:
                if u not in inputs:
                    c.add_gate("CZ", v, u)
    
    # draw(c, labels=True)

    return c

def to_stabilizer_tableau (d : Dict, quiet : bool = True) -> List[Tuple[VT, VT, int]]:
    """
    Convert a graph to a stabilizer tableau.
    
    Returns:
        A list of stabilizers representing the graph state
    """

    inputs = d["inputs"]
    adj = d["adjacency_list"]

    pivots = {i : -1 for i in inputs}

    out_to_in = {i : -1 for i in range(len(adj)) if i not in inputs}

    print(inputs)
    print(adj)

    for i in range(len(adj)):
        if i not in inputs:
            # print()
            neigh = adj[i]
            count = 0
            input = -1
            for n in neigh:
                if n in inputs:
                    count += 1
                    input = n
                    # print(n)
                    out_to_in[i] = n
            if count == 1:
                if pivots[input] == -1:
                    pivots[input] = i 


    stabilizers = [[Pauli(0,0,0) for _ in range(len(adj) - len(inputs)) ] for _ in range(len(adj) - 2 * len(inputs))]

    k = 0
    for i in range(len(inputs), len(adj)):
        if i not in pivots.values():
            # print("Scanning vertex", i)
            # print(k, i)
            stabilizers[k][i - len(inputs)] *= Pauli(0,1,0)
            # print(stabilizers[k])
            for x in adj[i]:
                if x not in inputs:
                    stabilizers[k][x - len(inputs)] *= Pauli(0,0,1)
            # print(stabilizers[k])
            y = pivots[out_to_in[i]] 
            stabilizers[k][y - len(inputs)] *= Pauli(0,1,0)
            # print(stabilizers[k])
            for x in adj[y]:
                if x not in inputs:
                    stabilizers[k][x- len(inputs)] *= Pauli(0,0,1)
            # print(stabilizers[k])
            k += 1

    return stabilizers

def to_distance_mzn(inputs, adj) -> str:
    dzn = ""

    # inputs = d["inputs"]
    dzn += f"I_nodes = {{{', '.join(str(x+1) for x in inputs)}}};\n"
    dzn += f"O_P_nodes = {{{', '.join(str(x+1) for x in range(len(adj)) if x not in inputs)}}};\n"

    dzn += f"[|"

    for i in range(len(adj)):
        row = ""
        for j in range(len(adj)):
            if j in adj[i]:
                row += "true, "
            else:
                row += "false, "
        dzn += row[:-2] + "|\n"

    dzn += "|];\n"

    dzn += "initial_lights = array1d[O_P_nodes, ["
    for i in range(len(adj)):
        if i not in inputs:
            row = "0, "
            dzn += row
    dzn += "]];\n"

    return dzn
