"""
Universal representation module
"""


__all__ = [

    "graph_state_to_universal_representation",
    "to_universal_graph_representation",  
    "implement_encoder",
    "distance_upper_bound",
    "stim_qasm_comply",
    "tableau_to_graph_encoder",
    "graph_to_universal_representation",
    "benchmark_from_graph_state",
    "UGR",
    "ZXCF",
    "to_stabilizer_tableau"
]



from pyzx.symbolic import Poly
from .graph_states import GraphState
from .simplify import is_graph_like, spider_simp, id_simp, clifford_simp
from fractions import Fraction
from .drawing import draw_d3, draw, draw_matplotlib
from .graph.base import ET, VT, BaseGraph, EdgeType, VertexType
from .graph import Graph
from .extract import connectivity_from_biadj, bi_adj
from typing import List, Tuple, Dict, Generic, cast, TypeVar
import itertools
from .circuit import Circuit
import pprint
from .linalg import Mat2
import time
import stim
import re


VT = TypeVar('VT', bound=int)
ET = TypeVar('ET')

class UGR():

    def __init__(self, inputs : List[int], adj : List[List[int]], pivots : List[int], local_cliffords : Dict[int, str]):
        self.inputs = inputs
        self.adj = adj
        self.pivots = pivots
        self.local_cliffords = local_cliffords


class ZXCF(Generic[VT, ET]):
    
    def __init__(self, graph: BaseGraph[VT, ET], inputs : List[VT],  pivots : List[VT]):
        self.inputs = inputs
        self.graph = graph
        self.pivots = pivots


def get_node_from_boundary(g : BaseGraph[VT, ET], v : VT) -> VT:
    """
    Get the internal node connected to a boundary vertex.

    Args:
        g (BaseGraph): The graph.
        v (VT): The vertex.

    Returns:
        int: the state vertex corresponding to the state.
    """

    # print("Getting internal node from boundary", v)
    # draw(g)

    ns = list(g.neighbors(v))

    return ns[0]

def get_neighbors(g : BaseGraph[VT, ET], v: VT) -> List[VT]:
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

def get_internal_inputs(g : BaseGraph[VT, ET]) -> List[VT]:
    """
    Get the internal input vertices.

    Returns:
        List[int]: The list of input vertices.
    """
    return [get_node_from_boundary(g, s) for s in g.inputs()]

def get_internal_outputs(g : BaseGraph[VT, ET]) -> List[VT]:
    """
    Get the internal output vertices.

    Returns:
        List[int]: The list of output vertices.
    """
    return [get_node_from_boundary(g, s) for s in g.outputs()]

def to_RRREF(g : BaseGraph[VT, ET], quiet : bool = True) -> List[VT]:
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


def remove_unitaries_input(g : BaseGraph[VT, ET], quiet : bool = True) -> None:
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

def remove_pivot_phases(g : BaseGraph[VT, ET], pivots : List[VT], quiet : bool = True) -> None:
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

def pivot(g : BaseGraph[VT, ET], x: VT, y: VT, quiet : bool = True, step : int = 0) -> None:
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



def remove_pivot_edges(g : BaseGraph[VT, ET], pivots : List[VT], quiet : bool = True) -> None:
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


def graph_state_to_universal_representation(g: GraphState[VT, ET], inputs : List[VT]) -> ZXCF:
    """Convert a GraphState to its uinversal representation.

    Args:
        g (GraphState): The GraphState to convert.
        inputs: List of input vertices
        outputs: List of output vertices

    Returns:
        BaseGraph: The converted BaseGraph.
    """
    g.to_canonical_form(quiet=True)
    # print(inputs)
    g2 = state_to_map(g, inputs)
    # print("Exporting to universal circuit...")
    remove_unitaries_input(g2)
    # print("to RRREF...")
    pivots = to_RRREF(g2, quiet = True)
    # print("Removing pivot phases...")
    remove_pivot_phases(g2, pivots, quiet = True)
    # print("Removing pivot edges...")
    remove_pivot_edges(g2, pivots, quiet = True)
    # print("Removing unitaries from inputs...")
    remove_unitaries_input(g2)

    return ZXCF(g2, inputs, pivots)

def benchmark_from_graph_state(g: GraphState[VT, ET]) -> Tuple[float, float, float, float]:

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

def to_universal_graph_representation(g: ZXCF[VT, ET], quiet : bool = True) -> UGR:
    """
    
    Convert a Clifford ZX diagram to its universal representation.

    Args:
        g : The Clifford ZX diagram as a BaseGraph.
        inputs : List of input vertices
        quiet : If True, suppresses output messages.

    Returns:
        BaseGraph: The adjacency matrix of the universal representation.
    """
    g2 = g.graph.clone()

    internal_inputs = get_internal_inputs(g2)
    internal_outputs = get_internal_outputs(g2)

    for v in g2.vertex_set():
        if g2.type(v) == VertexType.BOUNDARY:
            g2.remove_vertex(v)

    g2.set_inputs(tuple(internal_inputs))
    g2.set_outputs(tuple(internal_outputs))

    d = g2.to_dict()

    # d["local_cliffords"] = local_cliffords
    
    # d["inputs"] = internal_inputs
    # d["outputs"] = internal_outputs
    

    # g_filtered = d

    # boundary_ids = {v["id"] for v in d["vertices"] if v["t"] == VertexType.BOUNDARY}
    # g_filtered["vertices"] = [v for v in d["vertices"] if v["id"] not in boundary_ids]
    # g_filtered["edges"] = [e for e in d["edges"] if e[0] not in boundary_ids and e[1] not in boundary_ids]

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
            local_cliffords[vertex_map[v]] = "H"
    

    new_inputs =[vertex_map[x] for x in  d["inputs"]]

    pivots = [vertex_map[x] for x in g.pivots]

    # print(g_filtered["edges"])
    export = UGR(new_inputs, adjacency_list, pivots, local_cliffords)
    return export


def state_to_map(g : GraphState[VT, ET], inputs : List[VT]) -> BaseGraph[VT, ET]:
    """
    Export graph state to a ZX-diagram.
    """

    # expo
    export_g = g.get_graph().clone()
    outputs = [i for i in g.outputs() if i not in inputs]
    export_g.set_inputs(tuple(inputs))
    export_g.set_outputs(tuple(outputs))
        
    # g.get_graph().auto_detect_io()
    
    export_g.normalize()

    return export_g


def distance_upper_bound(d: UGR) -> int:
    """
    Compute an upper bound on the distance of the code represented by the graph state.

    Args:
        g (BaseGraph): The graph state.

    Returns:
        int: The upper bound on the distance.
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

def stim_qasm_comply(qasm: str) -> str:
    q = qasm
    q = re.sub(r'def\s+rx\(qubit q0\)\s*\{[^}]*\}\n+', '', q)
    q = re.sub(r'rx\s*\(\s*q\[(\d+)\]\s*\)\s*;', r'h q[\1];', q)
    q = re.sub(r'reset\s+q\[(\d+)\];', '', q)
    return q



# [stim.PauliString("+_Z_Z_"), stim.PauliString("+_ZXZX"), stim.PauliString("+_ZX_X")]
# [stim.PauliString("-_XY_X"), stim.PauliString("-_XYXX"), stim.PauliString("-YXXXY")]

def tableau_to_graph_encoder(code : List[str]) -> BaseGraph:
    

    code2 = [stim.PauliString(x) for x in code]
    print(code2)
    n = len(code2[0])
    k = n - len(code2)

    print(n, k)
    tableau = stim.Tableau.from_stabilizers(code2, allow_underconstrained=True)

    stabilizers = []

    for i in range (n - k):
        stabilizers.append(stim.PauliString(f"Z{i}") * stim.PauliString(n+k))

    for i in range(n-k, n): 
        stabilizers.append(stim.PauliString(f"Z{i}*Z{i+k}") * stim.PauliString(n+k)) 
        stabilizers.append(stim.PauliString(f"X{i}*X{i+k}") * stim.PauliString(n+k)) 

    state = stim.TableauSimulator()
    state.set_state_from_stabilizers(stabilizers)
    state.do_tableau(tableau, list(range(n)))
    t = state.current_inverse_tableau().inverse()

    qasm_random2 = t.to_circuit(method="graph_state").to_qasm(open_qasm_version=3)       
    pyzx_circ2 = Circuit.from_qasm(stim_qasm_comply(qasm_random2))
    g2 = pyzx_circ2.to_graph()
    input_state = "0"*(n+k)
    g2.apply_state(input_state)

    g2.set_inputs(g2.outputs()[n:n+k])
    # d = graph_to_universal_graph_representation(g2)
    # return d
    return g2
    




def graph_to_universal_representation(g: BaseGraph[VT, ET]) -> ZXCF:
    """
    Convert a Clifford ZX diagram to its universal representation.

    Args:
        g : The Clifford ZX diagram as a BaseGraph.

    Returns:
        BaseGraph: The universal representation of the GraphState.
    """
    inputs = list(g.inputs())
    g2 = GraphState(g)
    return graph_state_to_universal_representation(g2, inputs)

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
        return Pauli(a, b, c)

    def __repr__(self):
        phase = [1, 1j, -1, -1j][self.a]
        label = { (0,0):"I", (1,0):"X", (0,1):"Z", (1,1):"Y" }[(self.b,self.c)]
        return f"{phase}*{label}"



def implement_encoder(d : UGR) -> Circuit:

    inputs = d.inputs
    adj = d.adj
    local_cliffords = d.local_cliffords
    pivots = d.pivots

    # pivots = {i : -1 for i in inputs}
    out_to_in = {i : -1 for i in range(len(adj)) if i not in inputs}

    # for i in range(len(adj)):
    #     if i not in inputs:
    #         # print()
    #         neigh = adj[i]
    #         count = 0
    #         input = -1
    #         for n in neigh:
    #             if n in inputs:
    #                 count += 1
    #                 input = n
    #                 # print(n)
    #                 out_to_in[i] = n
    #         if count == 1:
    #             if pivots[input] == -1:
    #                 pivots[input] = i 

    
    n = len(adj)
    k = len(inputs)

    # print(inputs)

    c = Circuit(n)

    c.add_gate("H", n-1)
    for i in range(n-2, k-1, -1):
        c.add_gate("CNOT", n-1, i)
    
    for i in inputs:
        for j in adj[i]:
            if j not in pivots:
                c.add_gate("CZ", i, j)
        
    for i in inputs:
        c.add_gate("H", i)

    for v in range(n):
        if v not in inputs:
            for u in adj[v]:
                if u not in inputs:
                    c.add_gate("CZ", v, u)

    # for v in range(n):

    
    # draw(c, labels=True)

    return c

def to_stabilizer_tableau (d : UGR, quiet : bool = True) -> List[str]:
    """
    Convert a graph to a stabilizer tableau.
    
    Returns:
        A list of stabilizers representing the graph state
    """

    inputs = d.inputs
    adj = d.adj

    pivots = d.pivots

    outputs_no_pivots = set(range(len(adj))) - set(pivots)

    out_to_in = {i : set() for i in range(len(adj)) if i not in inputs}

    for o in range(len(adj)):
        if o not in inputs:
            for x in adj[o]:
                if x in inputs:
                    out_to_in[o].add(x)

    n = len(adj) - len(inputs)
    k = len(inputs)

    stabilizers = [stim.PauliString("I"*n) for _ in range(n-k)]

    for i in outputs_no_pivots:
        stabilizers[i - k] *= stim.PauliString(f"X{i-k}")
        for j in adj[i]:
            if j not in inputs:
                stabilizers[i - k] *= stim.PauliString(f"Z{j-k}")

        inp = out_to_in[i]
        for a in inp:
            p = pivots[a]
            stabilizers[i - k] *= stim.PauliString(f"X{p-k}")

            for q in adj[p]:
                if q not in inputs:
                    stabilizers[i-k] *= stim.PauliString(f"Z{q-k}")

    stabilizers = [str(x) for x in stabilizers]

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
