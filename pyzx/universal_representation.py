"""
Universal representation module
"""


__all__ = [
"to_universal_representation", "from_graph_state", "benchmark_from_graph_state", "to_universal_graph_representation"
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





def get_input_state(g : BaseGraph, v : int) -> Tuple[int, int]:
    """
    Get the input state of a vertex.

    Args:
        g (BaseGraph): The graph.
        v (int): The vertex.

    Returns:
        Tuple[int, int]: The input state as a tuple (qubit, row).
    """

    ns = list(g.neighbors(v))

    return ns[0]

def get_neigbbors(g, v: VT) -> List[VT]:
    """
    Get the neighbors of a state vertex.
    
    Args:
        v: The state vertex
    
    Returns:
        List of neighboring state vertices
        
    Raises:
        ValueError: If the vertex is not a state vertex
    """
    

    neighbors = [x for x in g.neighbors(v) if g.type(x) != VertexType.BOUNDARY]

    return neighbors

def get_inputs(g) -> List[int]:
    """
    Get the input vertices of the graph state.

    Returns:
        List[int]: The list of input vertices.
    """
    return [get_input_state(g, s) for s in g.inputs()]

def get_outputs(g) -> List[int]:
    """
    Get the output vertices of the graph state.

    Returns:
        List[int]: The list of output vertices.
    """
    return [get_input_state(g, s) for s in g.outputs()]

def to_RRREF(g : BaseGraph, quiet : bool = True) -> List[VT]:
    """
    Transform the graph state to a reduced row echelon form.
    
    Returns:
        List of pivot vertices
    """
    inputs = get_inputs(g)
    outputs = get_outputs(g)

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
        v = get_input_state(g, s)
        g.set_phase(v, 0)
        e = g.edge(v, s)
        g.set_edge_type(e, EdgeType.SIMPLE)

    for s1, s2 in itertools.product(ins,ins):
        v = get_input_state(g, s1)
        w = get_input_state(g, s2)
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
                neighbors = get_neigbbors(g, v)
                inputs_states = get_inputs(g)
                outputs_states = get_outputs(g)

                vin = -1

                for x in neighbors:
                    if x in inputs_states:
                        vin = x

                # self.get_graph().set_phase(vin, 0)

                neighborsin = [x for x in get_neigbbors(g, vin) if x in outputs_states]

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

    A = get_neigbbors(g,x) + [x]
    B = get_neigbbors(g,y) + [y]

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


def from_graph_state(g: GraphState, inputs, outputs) -> BaseGraph:
    """Convert a GraphState back to its uinversal representation.

    Args:
        g (GraphState): The GraphState to convert.

    Returns:
        BaseGraph: The converted BaseGraph.
    """
    g.to_canonical_form(quiet=True)

    draw(g, labels=True)

    # draw(g, labels=True, scale=120)

    state_to_map(g, inputs, outputs)

    draw(g, labels=True)

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

    draw(g, labels=True)

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

def to_universal_graph_representation(g: BaseGraph, inputs, outputs, quiet : bool = True) -> Dict:
    """Convert a Clifford ZX diagram to its universal representation.

    Args:
        g : The Clifford ZX diagram as a BaseGraph.
        quiet : If True, suppresses output messages.

    Returns:
        BaseGraph: The adjacency matrix of the universal representation.
    """
    # g = GraphState(g)
    # g.to_canonical_form(quiet=quiet)
    # g = from_graph_state(g)
    # draw(g, labels=True)

    # draw(g)

    g = to_universal_representation(g, inputs, outputs)

    # inputs = get_inputs(g)
    # outputs = get_outputs(g)
    d = g.to_dict()

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
    return g_filtered

def state_to_map(g, inputs, outputs) -> BaseGraph[VT, ET]:
    """
    Export graph state to a ZX-diagram.
    """

    g.set_inputs(inputs)
    g.set_outputs(outputs)
    g.normalize()

def to_universal_representation(g: BaseGraph, inputs, outputs) -> BaseGraph:
    """Convert a Clifford ZX diagram to its universal representation.

    Args:
        g : The Clifford ZX diagram as a BaseGraph.

    Returns:
        BaseGraph: The universal representation of the GraphState.
    """
    # draw(g, labels=True)
    g = GraphState(g)
    # draw(g, labels=True)
    # g.to_canonical_form(quiet=True)
    # state_to_map(g, inputs, outputs)
    return from_graph_state(g, inputs, outputs)


