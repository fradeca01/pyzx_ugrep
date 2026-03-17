"""
Universal Representation Module
-------------------------------
This module provides functionality for converting stabilizer codes into a Universal 
Graph Representation (UGR). 

"""


import itertools
import pprint
import re
import time
from fractions import Fraction
from typing import List, Tuple, Dict, Generic, TypeVar, Set, cast

import stim
from pyzx.circuit import Circuit
from pyzx.graph.base import BaseGraph, EdgeType, VertexType
from pyzx.symbolic import Poly

from .graph_states import GraphState
from .linalg import Mat2
from .extract import connectivity_from_biadj, bi_adj

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
    local_cliffords : Dict[int, str] 
        Dictionary mapping vertex to Clifford gate strings.
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
                neighbors = get_neighbors(g, v)
                inputs_states = get_inputs(g)
                outputs_states = get_outputs(g)

                vin = -1

                for x in neighbors:
                    if x in inputs_states:
                        vin = x

                neighborsin = [x for x in get_neighbors(g, vin) if x in outputs_states]

                for x in neighborsin:
                    g.add_to_phase(x, Fraction(1, 2))

                g.set_phase(vin, 0)

                go_on = True
                break

def pivot_operation(g : BaseGraph[VT, ET], x: VT, y: VT, quiet : bool = True, step : int = 0) -> None:
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
                pivot_operation(g, x, y, quiet = quiet, step=9)



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
    g.to_canonical_form(quiet=True)
    g2 = state_to_map(g, inputs)
    remove_unitaries_input(g2)
    pivots = to_RRREF(g2, quiet = True)
    remove_pivot_phases(g2, pivots, quiet = True)
    remove_pivot_edges(g2, pivots, quiet = True)
    remove_unitaries_input(g2)

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
            local_cliffords[vertex_map[v]] = "H"
    

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

# class Pauli:

#     # (a,b,c) represents i^a * X^b * Z^c
#     def __init__ (self, a, b, c):
#         self.a = a % 4
#         self.b = b % 2
#         self.c = c % 2

#     def __mul__(self, other):
#         s = (self.b * other.c - self.c * other.b) % 2 # commutation factor
#         a = (self.a + other.a + 2*s) % 4 # phase
#         b = (self.b + other.b) % 2 # X part
#         c = (self.c + other.c) % 2 # Z part
#         return Pauli(a, b, c)

#     def __repr__(self):
#         phase = [1, 1j, -1, -1j][self.a]
#         label = { (0,0):"I", (1,0):"X", (0,1):"Z", (1,1):"Y" }[(self.b,self.c)]
#         return f"{phase}*{label}"


#CHECK!!!!
def implement_encoder(d : UGR) -> Circuit:

    inputs = d.inputs
    adj = d.adj
    local_cliffords = d.local_cliffords
    pivots = d.pivots

    # pivots = {i : -1 for i in inputs}
    out_to_in = {i : -1 for i in range(len(adj)) if i not in inputs}

    
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
    outputs_no_pivots = list(set(range(len(adj))) - set(pivots) - set(inputs))

    print(inputs)
    print(pivots)
    print(outputs_no_pivots)

    out_to_in = {i : set() for i in range(len(adj)) if i not in inputs}


    for o in range(len(adj)):
        if o not in inputs:
            for x in adj[o]:
                if x in inputs:
                    out_to_in[o].add(x)


    n = len(adj) - len(inputs)
    k = len(inputs)
    print(out_to_in, n, k)

    stabilizers = [stim.PauliString("I"*n) for _ in range(n-k)]

    # print(stabilizers)
    s = 0
    for i in outputs_no_pivots:
        # print("HERE", f"X{i+2}")
        stabilizers[s] *= stim.PauliString(f"X{i - k}")
        for j in adj[i]:
            if j not in inputs:
                stabilizers[s] *= stim.PauliString(f"Z{j-k}")

        print(stabilizers[s])
        inp = out_to_in[i]
        for a in inp:
            p = pivots[a]
            stabilizers[s] *= stim.PauliString(f"X{p-k}")

            for q in adj[p]:
                if q not in inputs:
                    stabilizers[s] *= stim.PauliString(f"Z{q-k}")

        s += 1



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
