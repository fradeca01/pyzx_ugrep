
from pyzx.symbolic import Poly

from .simplify import is_graph_like, spider_simp, id_simp, clifford_simp
from fractions import Fraction
from .drawing import draw_d3, draw, draw_matplotlib
from .graph.base import ET, VT, BaseGraph, EdgeType, VertexType
from .graph import Graph
from .extract import connectivity_from_biadj, bi_adj
from typing import List, Tuple, Dict, Generic, cast
import itertools
from .circuit import Circuit


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



def remove_unitaries_input(g : BaseGraph, quiet : bool = True) -> None:
    """
    Remove unitary operations from input vertices.
    """
    ins = g.inputs()

    for s in ins:
        v = get_input_state(g, s)
        g.set_phase(v, 0)
        e = g.edge(v, s)
        g.set_edge_type(e, EdgeType.SIMPLE)

    for s1, s2 in ins:
        v = get_input_state(g, s1)
        w = get_input_state(g, s2)
        if g.connected(v, w):
            e = g.edge(v, w)
            g.remove_edge(e)


    if not quiet:
        print(f"Step: --- Removed unitaries from inputs")


def from_graph_state(g: GraphState) -> BaseGraph:
    """Convert a GraphState back to a BaseGraph.

    Args:
        g (GraphState): The GraphState to convert.

    Returns:
        BaseGraph: The converted BaseGraph.
    """
    g.to_canonical_form(quiet=True)
    g = g.state_to_map()


        print("Exporting to universal circuit...")
        print(f"Step {5}: {self.steps.get(5,'UNKNOWN')}")
        self.state_to_map(quiet = quiet)
        print(f"Step {7}: {self.steps.get(7,'UNKNOWN')}")
        self.to_RRREF(quiet = quiet)
        print(f"Step {8}: {self.steps.get(8,'UNKNOWN')}")
        self.remove_pivot_phases(quiet = True)
        print(f"Step {9}: {self.steps.get(9,'UNKNOWN')}")
        self.remove_pivot_edges(quiet = True)
        print(f"Step {6}: {self.steps.get(6,'UNKNOWN')}")
        self.remove_unitaries_input(quiet = quiet)
