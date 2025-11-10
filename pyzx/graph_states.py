"""
Graph states MODULE
"""


__all__ = [
    "GraphState",
]


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
import time


class GraphState(Generic[VT, ET]):
    """
    A class representing a graph state.
    
    It is a wrapper for BaseGraph and provides additional functionality for graph state operations.
    """

    to_canonical_steps = {
        1 : "Extracting paulis",
        2 : "Removing HS",
        3 : "Reordering H",
        4 : "Injecting paulis",
    }


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


    def __getattr__(self, name):
        """Redirect all other method calls to the underlying graph."""
        return getattr(self._graph, name)

    def get_states(self) -> List[VT]:
        """
        Get the list of state vertices.
        
        Returns:
            List of state vertices
        """
        return self._states
    
    def get_graph(self) -> BaseGraph[VT, ET]:
        """
        Get the underlying ZX diagram.
        
        Returns:
            The underlying ZX diagram
        """
        return self._graph

    def get_bound(self, s: VT) -> VT:
        """
        Get the boundary vertex connected to state vertex s.
        
        Args:
            s: The state vertex
        
        Returns:
            The boundary vertex connected to s
            
        Raises:
            ValueError: If the vertex doesn't have exactly one boundary vertex
        """
        
        bounds = [x for x in self.get_graph().neighbors(s) if x not in self.get_states()]

        if len(bounds) != 1:
            raise ValueError(f"Vertex {s} has {len(bounds)} boundary vertices: {bounds}, expected exactly 1")
        
        return bounds[0]
    

    def get_outputs(self) -> List[VT]:

        """
        Get the output vertices of the original ZX diagram.
        
        Returns:
            List of output states
        """
        outputs = self._outputs
        state_outputs = [list(self.get_graph().neighbors(v))[0] for v in outputs]
        # print(state_outputs)
        return state_outputs
      
    def get_inputs(self) -> List[VT]:
        """
        Get the input vertices of the original ZX diagram.
        
        Returns:
            List of inputs states
        """
        inputs = self.inputs()
        state_inputs = [list(self.get_graph().neighbors(v))[0] for v in inputs]
        # print(state_inputs)
        return state_inputs   
    
    def bound_edge(self, v: VT) -> ET:
        """
        Get the edge type connecting a state vertex to its boundary vertex.
        
        Args:
            v: The state vertex
        
        Returns:
            The edge connecting v to its boundary vertex
            
        Raises:
            ValueError: If the vertex is not a state vertex
        """
        
        if v not in self.get_states():
            raise ValueError(f"Vertex {v} is not a state vertex")

        bound = self.get_bound(v)
        edge = self.get_graph().edge(v, bound)

        return edge 
    

    def get_neigbbors(self, v: VT) -> List[VT]:
        """
        Get the neighbors of a state vertex.
        
        Args:
            v: The state vertex
        
        Returns:
            List of neighboring state vertices
            
        Raises:
            ValueError: If the vertex f`is not a state vertex
        """
        
        if v not in self.get_states():
            raise ValueError(f"Vertex {v} is not a state vertex")

        neighbors = [x for x in self.get_graph().neighbors(v) if x in self.get_states()]

        return neighbors
    
    def fix_ordering(self) -> None:
        g = Graph()
        ty = self.types()
        ph = self.phases()
        qs = self.qubits()
        rs = self.rows()
        vtab = dict()
        g.merge_vdata = self.merge_vdata 
        # print(self.get_graph().inputs())
        # print(self.get_inputs())
        # print(self.get_graph().outputs())
        # print(self.get_outputs())
        for v in self.get_outputs():
            i = g.add_vertex(ty[v],phase=ph[v])
            if v in qs: g.set_qubit(i,qs[v])
            if v in rs:
                g.set_row(i, rs[v])
            vtab[v] = i
            for k in self.vdata_keys(v):
                g.set_vdata(i, k, self.vdata(v, k))

        for v in self.get_inputs():
            i = g.add_vertex(ty[v],phase=ph[v])
            if v in qs: g.set_qubit(i,qs[v])
            if v in rs:
                g.set_row(i, rs[v])
            vtab[v] = i
            for k in self.vdata_keys(v):
                g.set_vdata(i, k, self.vdata(v, k))                        

        for v in self.get_graph().outputs():
            i = g.add_vertex(ty[v],phase=ph[v])
            if v in qs: g.set_qubit(i,qs[v])
            if v in rs:
                g.set_row(i, rs[v])
            vtab[v] = i
            for k in self.vdata_keys(v):
                g.set_vdata(i, k, self.vdata(v, k))

        for v in self.get_graph().inputs():
            i = g.add_vertex(ty[v],phase=ph[v])
            if v in qs: g.set_qubit(i,qs[v])
            if v in rs:
                g.set_row(i, rs[v])
            vtab[v] = i
            for k in self.vdata_keys(v):
                g.set_vdata(i, k, self.vdata(v, k))   

        new_inputs = tuple(vtab[i] for i in self.inputs())
        new_outputs = tuple(vtab[i] for i in self.outputs())
        g.set_inputs(new_inputs)
        g.set_outputs(new_outputs)
        
        for e in self.edges():
            s, t = self.edge_st(e)
            new_e = g.add_edge((vtab[s], vtab[t]), self.edge_type(e))
            g.set_edata_dict(new_e, self.edata_dict(e))

        self._graph = g
        self._states = [vtab[v] for v in self._states]
        self._inputs = [vtab[v] for v in self._inputs]
        self._outputs = [vtab[v] for v in self._outputs]

    def cji(self) -> None:
        qs = self.get_states()
        inputs = self.get_inputs()

        for j in range(len(inputs)):
            # print(inputs[j], len(qs))
            bound = self.get_bound(inputs[j])
            self.set_qubit(inputs[j], len(qs) - len(inputs) + j  )
            self.set_qubit(bound, len(qs) - len(inputs) + j )
            # print(self.qubit(inputs[j]), self.qubit(bound))


    

    def __init__(self, graph: BaseGraph[VT, ET], quiet : bool = True) -> None:
        """
        Initialize an (extended) GraphState from a Clifford ZX-diagram.
        
        Args:
            graph: A Clifford ZX-diagram. 
            
        Raises:
            ValueError: If the input is not a valid Clifford ZX-diagram
        """

        # Check if the diagram is Clifford before processing
        for v in graph.vertices():
            if graph.type(v) == VertexType.BOUNDARY:
                continue
            phase = graph.phase(v)
            if isinstance(phase, Poly):
                raise ValueError(f"Vertex {v} has a non-Clifford phase: {phase}")
            if phase % Fraction(1, 2) != 0:
                raise ValueError(f"Vertex {v} has a non-Clifford phase: {phase}")

        graph.auto_detect_io()


        clifford_simp(graph, quiet=quiet) # O(n)
        graph.normalize()
        
        self._graph = graph
        
        states = [x for x in graph.vertex_set() if graph.types()[x] != VertexType.BOUNDARY]
        self._states = states
        
        self._inputs = graph.inputs()
        self._outputs = graph.outputs()
        
        self.fix_free_edges()
        # self.fix_ordering()
        self.cji()
        self.normalize_graph_state(quiet=quiet)
        self.auto_detect_io()
        self.validate(quiet = quiet)


    def pretty_print(self, draw : bool = False) -> None:
        """
        Print the graph state in a human-readable format.

        Args:
            draw: If True, visualize the graph state
        """

        print("Graph State:")
        print(f"States: {self._states}")
        print(f"Graph: {self.get_graph()}")
        for i in self.get_states():
            bound = self.get_bound(i)
            print(f"State {i}: Phase = {self.get_graph().phase(i)}, Type = {self.get_graph().type(i)}, Bound: {bound}, Type: {self.get_graph().type(bound)}, Phase: {self.get_graph().phase(bound)}")

        if draw:
            draw(self.get_graph(), labels=True)



    def validate(self, quiet : bool = True) -> bool:
        
        """
        Checks if a ZX-diagram is extended graph-state form: 
         - only contains Z-spiders which are connected by Hadamard edges.
         - checks that each boundary vertex is connected to a Z-spider,
         - There are no interior spiders.
         - There are no self-loops or parallel edges,
         - Only Clifford phases (multiples of pi/2),
         - Each Z-spider is connected to exactly one boundary. 

        Args:
            quiet: If False, display intermediate steps

        Returns:
            True if valid graph state, False otherwise
        
        """

        g = self.get_graph()

        # if not quiet: draw_d3(self._graph, labels=True, scale=65)

        # checks that all spiders are Z-spiders
        for v in self.get_states():
            if g.type(v) not in [VertexType.Z, VertexType.BOUNDARY]:
                if not quiet:
                    print(f"Vertex {v} is not a Z-spider or boundary vertex, type: {g.type(v)}")
                return False

        for v1, v2 in itertools.combinations(self.get_states(), 2):
            if not g.connected(v1, v2):
                continue

            # Z-spiders are only connected via Hadamard edges
            if g.type(v1) == VertexType.Z and g.type(v2) == VertexType.Z \
            and g.edge_type(g.edge(v1, v2)) != EdgeType.HADAMARD:
                if not quiet:
                    print(f"Z-spiders {v1} and {v2} are not connected by a Hadamard edge")
                return False

            g.num_edges(v1, v2) == 1  # no parallel edges

        # no self-loops
        for v in self.get_states():
            if g.connected(v, v):
                if not quiet:
                    print(f"Vertex {v} has a self-loop")
                return False

  
        # every I/O is connected to a spider
        bs = [v for v in g.vertices() if g.type(v) == VertexType.BOUNDARY]
        for b in bs:
            if g.vertex_degree(b) != 1 :
                if not quiet:
                    print(f"Boundary vertex {b} is not connected to a spider")
                return False

        # every Z-spider is connected to at most and at least one I/O
        for z in self.get_states():
            b_neighbors = [n for n in g.neighbors(z) if n not in self.get_states()]
            if len(b_neighbors) != 1:
                if not quiet:
                    print(f"Z-spider {z} is not connected to exactly one boundary vertex, found: {len(b_neighbors)}")
                return False

        # Only clifford spiders
        for v in self._states:
            a = self.get_graph().phase(v) 
            if type(a) == Poly:
                if not quiet:
                    print(f"Vertex {v} has a non-clifford phase: {a}")
                return False
            else:
                a = cast(Fraction, a) 
            if a % Fraction(1, 2) != 0:
                if not quiet:
                    print(f"Vertex {v} has a non-clifford phase: {a}")
                return False
        
        if not quiet:
            # print(f"Step {step}: {self.steps.get(step,'UNKNOWN')} --- Graph state is valid:")
            draw_d3(self.get_graph(), labels=True, scale=40)

        return True
        
  
    def local_comp_SH(self, v: VT, quiet : bool = True, step : int = 0) -> None:
        """
        Perform a local complementation with SH ending on vertex v.

        Effectively remves the phase on vertex v and adds pi/2 to each neighbor of v.

        Args:
            v: The vertex to apply the local complementation to.
            
        Raises:
            ValueError: If the graph is not a valid graph state or LC conditions not met
        """


        bound = self.get_bound(v)
        new_bound = self.get_bound(bound)
        neighbors = self.get_neigbbors(v)

        if not quiet:
            print(f"Step {step}: {self.to_canonical_steps.get(step,'UNKNOWN')} --- Performing local complementation SH on vertex {v} with bound {bound} and neighbors {neighbors}")

        bound_phase = self.get_graph().phase(bound)
        phase = self.phase(v)
        
        if phase >= 1:
            self.get_graph().add_to_phase(bound, +1)
            bound_phase = self.get_graph().phase(bound)

        self.get_graph().remove_vertex(bound)
        self.get_graph().add_edge((new_bound, v), EdgeType.HADAMARD)

        for x in neighbors:
            self.get_graph().add_to_phase(x, Fraction(1, 2))

        for x in neighbors:
            for y in neighbors:
                if x >= y:
                    continue
                connected = self._graph.connected(x, y)
                if connected == 0:
                    self._graph.add_edge(edge_pair=(x, y), edgetype=EdgeType.HADAMARD)
                else:
                    self._graph.remove_edge(self._graph.edge(x, y))
        
        # self.push_out_paulis(quiet=quiet, step = 3)
 
        if bound_phase > 1:
            for x in neighbors:
                if not quiet:
                    print("Adding phase 1 to neighbor", x)
                self.get_graph().add_to_phase(x, 1)

        if not self.validate(quiet=quiet):
            raise ValueError("Graph is not a valid graph state")


    def local_comp_HS(self, v: VT, quiet: bool = True) -> None:

        """
        Perform a local complementation based rule with HS ending on vertex v. 

        The diagram is modified in place:
            - The hadamard on vertex v is removed
            - We substract pi to the phase of v
            - we add -pi/2 to the phase of each neighbor of v
            - We local complement on the neighborhood of v

        Args:
            v: The vertex to apply the local complementation to.
            
        Raises:
            ValueError: If the graph is not a valid graph state or LC conditions not met
        """

        bound = self.get_bound(v)
        neighbors = self.get_neigbbors(v)
        a = self.get_graph().phase(v)
        edge = self.get_graph().edge(bound, v)
        
        if not quiet:
            print(f"Step {2}: {self.to_canonical_steps.get(2,'UNKNOWN')} --- Performing local complementation HS on vertex {v} (phase: {a}) with bound {bound} and neighbors {neighbors}")

        if not (a % 1 == Fraction(1, 2) and self.get_graph().edge_type(edge) == EdgeType.HADAMARD):
            raise ValueError("This LC rule must be applied with a HS ending")

        for x in neighbors:
            if a > Fraction(1,2):
                self.get_graph().add_to_phase(x, +Fraction(1,2))
            else:
                self.get_graph().add_to_phase(x, -Fraction(1, 2))

        self.get_graph().add_to_phase(v, +1) 
        self.get_graph().set_edge_type(edge, EdgeType.SIMPLE)

        #Ss                
        for x in neighbors:
            for y in neighbors:
                if x >= y:
                    continue
                connected = self.get_graph().connected(x, y)
                if connected == 0:
                    self.get_graph().add_edge(edge_pair=(x, y), edgetype=EdgeType.HADAMARD)
                else:
                    self.get_graph().remove_edge(self.get_graph().edge(x, y))

        # self.push_out_paulis(quiet=quiet, step = 2)

        if not self.validate(quiet=quiet):
            raise ValueError("Graph is not a valid graph state")

    def pivot(self, x: VT, y: VT, quiet : bool = True) -> None:
        """
        Perform a pivot operation between vertices x and y in the graph state.
        
        Args:
            x: First vertex for pivot operation
            y: Second vertex for pivot operation
            quiet: If False, display intermediate steps and print pivot operations
            
        Raises:
            ValueError: If the graph is not in a valid state for pivoting
        """

        if not quiet:
            print(f"-> Pivoting between vertices {x} and {y}")
    
        A = self.get_neigbbors(x) + [x]
        B = self.get_neigbbors(y) + [y]

        phase_x = self.phase(x)
        phase_y = self.phase(y)

        for v in A:
            if v in B:
                if v != x and v != y:
                    if not quiet:
                        print(f"---> Adding phase 1 to vertex {v} in intersection of A and B")
                    self.get_graph().add_to_phase(v, 1)

        # Add/remove edges between A and B sets
        for i in range(len(A)):
            for j in range(len(B)):
                if A[i] == B[j]:
                    continue
                elif not self.get_graph().connected(A[i], B[j]):
                    self.get_graph().add_edge((A[i], B[j]), edgetype=EdgeType.HADAMARD)
                else:
                    self.get_graph().remove_edge(self.get_graph().edge(A[i], B[j]))

        if not self.validate(quiet=quiet):
            raise ValueError("Graph is not a valid graph state")

        def flip_edge(type_e: EdgeType) -> EdgeType:
            if type_e == EdgeType.SIMPLE:
                return EdgeType.HADAMARD
            else:
                return EdgeType.SIMPLE
            
        if not quiet:
            print(f"---> Phases before fixing pivots: x: {phase_x % 1}, y: {phase_y % 1}")

        # assert not (phase_x % 1 == Fraction(1,2) and phase_y % 1 == Fraction(1,2)), "Both vertices cannot have phase pi/2"  
        # assert not (phase_x % 1 == Fraction(1,2) and type_x == EdgeType.HADAMARD), "Vertex x cannot have phase pi/2 and simple edge"
        # assert not (phase_y % 1 == Fraction(1,2) and type_y == EdgeType.HADAMARD), "Vertex x cannot have phase pi/2 and simple edge"

        def fix_vertex(p, phase_p):
            if phase_p % 1 == Fraction(1,2):
                new = self._graph.add_vertex(VertexType.Z)
                self.get_graph().set_qubit(new, self.get_graph().qubit(p))
                self.get_graph().set_row(new, self.get_graph().row(p) + 1)
                self.get_graph().set_phase(new, phase_p)
                self.get_graph().set_phase(p, 0)
                bound = self.get_bound(p)
                self._graph.remove_edge(self._graph.edge(bound, p))
                self._graph.add_edge((new, p), EdgeType.HADAMARD)
                self._graph.add_edge((new, bound), EdgeType.SIMPLE)
            else:
                edge_p = self._graph.edge(p, self.get_bound(p))
                type_p = self.edge_type(self.bound_edge(p))
                self._graph.set_edge_type(edge_p, flip_edge(type_p))    

        fix_vertex(x, phase_x)
        fix_vertex(y, phase_y)

        if phase_x == 1:
            self.get_graph().add_to_phase(x, -1)
            for a in self.get_neigbbors(x):
                self.get_graph().add_to_phase(a, 1)

        if phase_y == 1:
            self.get_graph().add_to_phase(y, -1)
            for a in self.get_neigbbors(y):
                self.get_graph().add_to_phase(a, 1)

        if not self.validate(quiet=quiet):
            raise ValueError("Graph is not a valid graph state")


    def fix_free_edges(self) -> None:
        """
        Fix input/output connections by ensuring each state vertex has exactly one boundary connection. Add new intermediate state vertices if necessary.
        
        Raises:
            ValueError: If the graph is not graph-like
        """
        if not is_graph_like(self.get_graph()):
            raise ValueError("Graph is not graph-like")

        for v in self._states:
            bound = [x for x in self.get_graph().neighbors(v) if x not in self._states]
            if len(bound) > 1:
                # print("Vertex:", v, "Phase:", g.phase(v), "Type:", g.types()[v])
                for i in range(len(bound) - 1):
                    edge_type = self.get_graph().edge_type(self.get_graph().edge(bound[i], v))
                    new = self.get_graph().add_vertex(VertexType.Z)
                    self._states.append(new)
                    self.set_qubit(new, self.qubit(bound[i]))
                    if edge_type == EdgeType.HADAMARD:
                        self.get_graph().add_edge((bound[i], new), EdgeType.SIMPLE)
                        # self.get_graph().add_edge((new, v), EdgeType.HADAMARD)
                    else:
                        self.get_graph().add_edge((bound[i], new), EdgeType.HADAMARD)

                    self.get_graph().add_edge((new, v), EdgeType.HADAMARD)
                    self.get_graph().remove_edge(self.get_graph().edge(bound[i], v))


    def normalize_graph_state(self, quiet : bool = True) -> None:
        """
        Normalize the graph state by setting proper qubit and row assignments.
        
        Raises:
            ValueError: If the graph is not a valid graph state
        """
        if not self.validate(quiet=quiet):
            raise ValueError("Graph is not a valid graph state")
        
        # self.normalize()

        states = self.get_states()
       
        for i in range(len(states)):
            # self.get_graph().set_qubit(self._states[i], i)
            self.get_graph().set_row(self._states[i], (self.get_graph().qubit(self._states[i]) % 2) * 4)
            bound = self.get_bound(self._states[i])
            # self.get_graph().set_qubit(bound, i)
            self.get_graph().set_row(bound, 10)


    # def state_to_map(self, original_io : bool = True) -> BaseGraph[VT, ET]:
    #     """
    #     Export graph state to a ZX-diagram.
    #     """

    #     if original_io:
    #         self.get_graph().set_inputs(self._inputs)
    #         self.get_graph().set_outputs(self._outputs)
        
    #     # print(self._inputs)
    #     # print(self._outputs)
        
    #     # draw(self.get_graph(), labels=True)


    #     export_g = self.get_graph().copy()
    #     self.get_graph().auto_detect_io()

    #     # draw(export_g, labels=True)


    #     export_g.normalize()

    #     return export_g


    def remove_HS(self, quiet: bool = True) -> None:
        """
        Remove all HS local Clifford operations from the graph state.
        
        Args:
            quiet: If False, display intermediate steps.

        Raises:
            ValueError: If the graph is not a valid graph state
        """
        go_on = True
        while go_on:
            go_on = False
            for v in self._states:
                phase = self.get_graph().phase(v)
                edge = self.get_graph().edge(self.get_bound(v), v)
                edge_type = self.get_graph().edge_type(edge)
                
                if (phase % 1 == Fraction(1, 2) and edge_type == EdgeType.HADAMARD):
                    self.local_comp_HS(v, quiet=quiet)
                    go_on = True
                    break
        
        if not quiet:
            print(f"Step 2: {self.to_canonical_steps.get(2,'UNKNOWN')} --- Removing HS from graph ended")

        if not self.validate(quiet=quiet):
            raise ValueError("Graph is not a valid graph state")


    def reorder_H(self, quiet: bool = True) -> None:
        """
        Apply a pivoting strategy to reorder Hadamard edges in the graph state to satisfy the canonical ordering conditions.
     
        Args:
            quiet: If False, display intermediate steps and print pivot operations.
        """
        go_on = True
        while go_on:
            go_on = False
            for x in self._states:
                edge = self.get_graph().edge(x, self.get_bound(x))
                if self.get_graph().edge_type(edge) == EdgeType.HADAMARD:
                    neigh = [v for v in self.get_graph().neighbors(x) if v in self.get_states()]
                    for y in neigh:
                        if y < x:
                            self.pivot(y, x, quiet = quiet)
                            go_on = True
                            break

        for s in self.get_states():
            bound = self.get_bound(s)
            bound_phase = self.get_graph().phase(bound)
            edge_type = self.edge_type(self.bound_edge(s))

            if edge_type == EdgeType.SIMPLE and bound_phase % 1 == Fraction(1, 2):
                new_bound = self.get_bound(bound)
                self.get_graph().remove_vertex(bound)
                self.get_graph().add_edge((new_bound, s), EdgeType.SIMPLE)
                self.get_graph().add_to_phase(s, bound_phase)
                
            if edge_type == EdgeType.HADAMARD and bound_phase % 1 == Fraction(1, 2):
                self.local_comp_SH(s, quiet= quiet, step = 3)
        
        if not self.validate(quiet=quiet):
            raise ValueError("Graph is not a valid graph state")

    

    def validate_canonical_form(self, quiet : bool = True) -> bool:

        states = self.get_states()

        if not self.validate(quiet=quiet):
            return False
    
        for s1, s2 in itertools.product(states, states):
            # print(s1, s2)
            if s1 < s2 and self.connected(s1, s2):
                edge1 = self.edge_type(self.bound_edge(s1))
                edge2 = self.edge_type(self.bound_edge(s2))
                # print(edge2)
                if edge2 == EdgeType.HADAMARD:
                    if not quiet:
                        print(f"Vertices {s1} and {s2} are connected and {s2} has a Hadamard edge to its boundary")
                    return False

        return True

        
    def to_canonical_form(self, quiet : bool = True):

        """
        Reduce the extended graph state to its canonical form.

        Args:
            quiet: If False, display intermediate steps and print pivot operations
        """     
        if not quiet:
            print(f"STARTING: CANONICAL FORM")
            print()

        if not self.validate(quiet = quiet):
            raise ValueError("Graph is not a valid graph state")
        
        if not quiet:
            print("Transforming to canonical form...")
        if not quiet:
            print(f"Step {2}: {self.to_canonical_steps.get(2,'UNKNOWN')}")
        self.remove_HS(quiet=quiet)
        if not quiet:
            print(f"Step {3}: {self.to_canonical_steps.get(3,'UNKNOWN')}")
        self.reorder_H(quiet = quiet)
        if not quiet:
            print(f"Step {4}: {self.to_canonical_steps.get(4,'UNKNOWN')}")

        if not quiet:
            print("---------------------------------")
            print("OUTPUT:...................")
        if not self.validate(quiet = quiet):
            raise ValueError("Graph is not a valid graph state") 
        
    
    def benchmark_to_canonical_form(self):        
        start = time.perf_counter()
        self.remove_HS(quiet=True)
        end1 = time.perf_counter()
        self.reorder_H(quiet=True)
        end2 = time.perf_counter()

        if not self.validate():
            raise ValueError("Graph is not a valid graph state") 

        return (end1 - start, end2 - end1)





    def to_stabilizer_tableau (self, quiet : bool = True) -> List[Tuple[VT, VT, int]]:
        """
        Convert the graph state to a stabilizer tableau.
        
        Returns:
            A list of stabilizers representing the graph state
        """

        # CHANGE WITH CORRECT METHOD WHEN IMPLEMENTED
        if not self.validate():
            raise ValueError("Graph is not a valid graph state")

        stabilizers = []

        n = len(self.get_outputs())
        
        map = {v : i for i, v in enumerate(self.get_outputs())}

        pivots = self.get_pivots()
        outs_no_pivots = [v for v in self.get_outputs() if v not in pivots]
        inputs = self.get_inputs()

        for v in outs_no_pivots:
            s = ["I" for _ in range(n)]
            s[map[v]] = "X"
            for x in self.get_graph().neighbors(v):
                if x in self.get_ouputs():
                    s[map[x]] = "Z"
        return stabilizers

