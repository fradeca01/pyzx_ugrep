"""
Graph states MODULE
"""


__all__ = [
    "GraphState",
]


from pyzx.symbolic import Poly

from .simplify import is_graph_like, spider_simp, id_simp, clifford_simp
from fractions import Fraction
from .d3 import draw_d3
from .graph.base import ET, VT, BaseGraph, EdgeType, VertexType
from .extract import connectivity_from_biadj, bi_adj
from typing import List, Tuple, Dict, Generic, cast
import itertools
from .circuit import Circuit

class GraphState(Generic[VT, ET]):
    """
    A class representing a graph state.
    
    It is a wrapper for BaseGraph and provides additional functionality for graph state operations.
    """

    steps = {
        1 : "Extracting paulis",
        2 : "Removing HS",
        3 : "Reordering H",
        4 : "Injecting paulis",
        5 : "Converting to circuit",
        6 : "Removing unitaries from inputs",
        7 : "Transofrm to RREF",
        8 : "Removing pivot phases",
        9 : "Removing pivot edges"
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

    def bound_edge_type(self, v: VT) -> ET:
        """
        Get the edge connecting a state vertex to its boundary vertex.
        
        Args:
            v: The state vertex
        
        Returns:
            The edge connecting v to its boundary vertex
            
        Raises:
            ValueError: If the vertex doesn't have exactly one boundary vertex
        """
        
        if v not in self.get_states():
            raise ValueError(f"Vertex {v} is not a state vertex")

        bound = self.get_bound(v)
        edge = self.get_graph().edge(v, bound)
        edge_type = self.get_graph().edge_type(edge)

        return edge_type 
    

    def get_neigbbors(self, v: VT) -> List[VT]:
        """
        Get the neighbors of a state vertex.
        
        Args:
            v: The state vertex
        
        Returns:
            List of neighboring state vertices
            
        Raises:
            ValueError: If the vertex is not a state vertex
        """
        
        if v not in self.get_states():
            raise ValueError(f"Vertex {v} is not a state vertex")

        neighbors = [x for x in self.get_graph().neighbors(v) if x in self.get_states()]

        return neighbors

    def __init__(self, graph: BaseGraph[VT, ET]) -> None:
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

        #Simplify ZX diagram to be a graph-state
        clifford_simp(graph, quiet=True) # O(n)

        self._graph = graph
        states = [x for x in graph.vertex_set() if graph.types()[x] != VertexType.BOUNDARY]
        self._states = states
        self._pivots = None
        self._paulis = None

        self.fix_free_edges(quiet=True)
        self.normalize_graph_state(quiet=True)

        self.validate()

    def pretty_print(self, draw : bool = False) -> None:
        """
        Print the graph state in a human-readable format.
        """

        print("Graph State:")
        print(f"States: {self._states}")
        print(f"Graph: {self.get_graph()}")
        for i in self.get_states():
            bound = self.get_bound(i)
            print(f"State {i}: Phase = {self.get_graph().phase(i)}, Type = {self.get_graph().type(i)}, Bound: {bound}, Type: {self.get_graph().type(bound)}, Phase: {self.get_graph().phase(bound)}")

        if draw:
            draw_d3(self.get_graph(), labels=True, scale=65)

    def __getattr__(self, name):
        """Redirect all other method calls to the underlying graph."""
        return getattr(self._graph, name)

    def validate(self, quiet : bool = True, step : int = 0) -> bool:
        
        """
        Checks if a ZX-diagram is extended graph-state: 
         - only contains Z-spiders which are connected by Hadamard edges.
         - checks that each boundary vertex is connected to a Z-spider,
         - There are no interior spiders.
         - There are no self-loops or parallel edges,
         - Only Clifford phases (multiples of pi/2),
         - Each Z-spider is connected to exactly one boundary. 

        Validate if this is a proper extended graph state.
        
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
    
    def get_states(self) -> List[VT]:
        """
        Get the list of state vertices.
        
        Returns:
            List of state vertices
        """
        return self._states
    
    def get_graph(self) -> BaseGraph[VT, ET]:
        """
        Get the underlying graph.
        
        Returns:
            The underlying graph
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
        
        bounds = [x for x in self.get_graph().neighbors(s) if x not in self._states]
        if len(bounds) != 1:
            raise ValueError(f"Vertex {s} has {len(bounds)} boundary vertices: {bounds}, expected exactly 1")
        
        return bounds[0]
    

    def get_outputs(self) -> List[VT]:
        """
        Get the output vertices of the graph state.
        
        Returns:
            List of output vertices
        """
        return [v for v in self.get_states() if self.get_bound(v) in self.get_graph().outputs()]
    
    def get_inputs(self) -> List[VT]:
        """
        Get the inputs vertices of the graph state.
        
        Returns:
            List of inputs vertices
        """
        return [v for v in self.get_states() if self.get_bound(v) in self.get_graph().inputs()]
    
    def get_pivots(self) -> List[VT]:
        """
        Get the pivot vertices of the graph state.
        
        Returns:
            List of pivot vertices
        """
        if self._pivots is None:
            raise ValueError("Pivots have not been computed yet. Call to_RRREF() first.")
        return self._pivots    
    
    def get_phase(self, v: VT) -> Fraction:
        """
        Get the phase of a state vertex.
        
        Args:
            v: The state vertex
        
        Returns:
            The phase of the vertex
            
        Raises:
            ValueError: If the vertex is not a state vertex
        """
        
        if v not in self.get_states():
            raise ValueError(f"Vertex {v} is not a state vertex")

        a = self.get_graph().phase(v)

        return a
    
    def local_comp_pivot(self, v: VT, quiet : bool = True) -> None:
        """
        Perform a local complementation pivot on vertex v.

        Args:
            v: The vertex to apply the local complementation to.
            
        Raises:
            ValueError: If the graph is not a valid graph state or LC conditions not met
        """

        if not quiet:
            print(f"Performing local complementation pivot on vertex {v} with bound {bound} and neighbors {neighbors}")

        if not self.validate(quiet=quiet):
            raise ValueError("Graph is not a valid graph state")
        
        bound = self.get_bound(v)
        neighbors = self.get_neigbbors(v)

        a = self.get_phase(v)

        

        if not (a == 0 and self.bound_edge_type(v) == EdgeType.HADAMARD):
            raise ValueError("This LC must be applied with a pivot ending")

        for x in neighbors:
            self.get_graph().add_to_phase(x, 1)

        for x in neighbors:
            for y in neighbors:
                if x >= y:
                    continue
                connected = self.get_graph().connected(x, y)
                if connected == 0:
                    self._graph.add_edge(edge_pair=(x, y), edgetype=EdgeType.HADAMARD)
                else:
                    self._graph.remove_edge(self._graph.edge(x, y))
        
        if not quiet:
            draw_d3(self.get_graph(), labels=True, scale=65)

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
        neighbors = self.get_neigbbors(v)

        if not quiet:
            print(f"Step {step}: {self.steps.get(step,'UNKNOWN')} --- Performing local complementation SH on vertex {v} with bound {bound} and neighbors {neighbors}")

        a = self.get_phase(v)

        # if not (a == Fraction(1, 2) and self._graph.edge_type(self._graph.edge(bound, v)) == EdgeType.HADAMARD):
        #     raise ValueError("This LC must be applied with a SH ending")
        
        self.get_graph().set_phase(v, 0)

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

        if not self.validate(quiet=quiet, step = 3):
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
            print(f"Step {2}: {self.steps.get(2,'UNKNOWN')} --- Performing local complementation HS on vertex {v} (phase: {a}) with bound {bound} and neighbors {neighbors}")

        if not (a % 1 == Fraction(1, 2) and self.get_graph().edge_type(edge) == EdgeType.HADAMARD):
            raise ValueError("This LC rule must be applied with a HS ending")

        for x in neighbors:
            if a > Fraction(1,2):
                self.get_graph().add_to_phase(x, +Fraction(1,2))
            else:
                self.get_graph().add_to_phase(x, -Fraction(1, 2))

        # if a > Fraction(1,2):
            # self._graph.add_to_phase(v, -1)

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

        if not self.validate(quiet=quiet, step = 2):
            raise ValueError("Graph is not a valid graph state")

    def pivot(self, x: VT, y: VT, quiet : bool = True, step : int = 0) -> None:
        """
        Perform a pivot operation between vertices x and y in the graph state.
        
        Args:
            x: First vertex for pivot operation
            y: Second vertex for pivot operation
            
        Raises:
            ValueError: If the graph is not in a valid state for pivoting
        """

        if not quiet:
            print(f"Step {step}: {self.steps.get(step,'UNKNOWN')} --- Pivoting between vertices {x} and {y}")
    
        A = self.get_neigbbors(x) + [x]
        print(A)
        B = self.get_neigbbors(y) + [y]
        print(B)
        for v in A:
            if v in B:
                if v != x and v != y:
                    print(f"Step {step}: {self.steps.get(step,'UNKNOWN')} --- Adding phase 1 to vertex {v} in intersection of A and B")
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

        if not self.validate(quiet=quiet, step = step):
            raise ValueError("Graph is not a valid graph state")
        # Flip edge types (careful with phases here)
        def flip_edge(type_e: EdgeType) -> EdgeType:
            if type_e == EdgeType.SIMPLE:
                return EdgeType.HADAMARD
            else:
                return EdgeType.SIMPLE
            
        phase_x = self.get_phase(x)
        phase_y = self.get_phase(y)

        print(f"Phases before fixing pivots: x: {phase_x % 1}, y: {phase_y % 1}")

        assert phase_x % 1 != Fraction(1,2) or phase_y % 1 != Fraction(1,2), "If everything correct impossible that the two pivots have phase 1/2"

        if phase_x % 1 == Fraction(1,2):
            self.local_comp_SH(x, quiet=quiet, step = step)
        elif phase_y % 1 == Fraction(1,2):
            self.local_comp_SH(y, quiet=quiet, step = step)
            
        def fix_pivot(p, phase_p):
            print(phase_p)
            print(f"Fixing pivot vertex {p}")
            neigh_p = self.get_neigbbors(p)
            edge_p = self.get_graph().edge(p, self.get_bound(p))
            type_p = self.get_graph().edge_type(edge_p)
            self.get_graph().set_edge_type(edge_p, flip_edge(type_p))

            if phase_p >= 1:
                for a in neigh_p:
                    self.get_graph().add_to_phase(a, 1)
                
                if phase_p % 1 != Fraction(1, 2):
                    self.get_graph().add_to_phase(p, -1)
            

        fix_pivot(x, phase_x)
        fix_pivot(y, phase_y)

        # if step != 9:
        #     self.push_out_paulis(quiet=quiet, step = step)



    def fix_free_edges(self, quiet : bool = True) -> None:
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
                    if edge_type == EdgeType.HADAMARD:
                        self.get_graph().add_edge((bound[i], new), EdgeType.SIMPLE)
                        # self.get_graph().add_edge((new, v), EdgeType.HADAMARD)
                    else:
                        self.get_graph().add_edge((bound[i], new), EdgeType.HADAMARD)

                    self.get_graph().add_edge((new, v), EdgeType.HADAMARD)
                    self.get_graph().remove_edge(self.get_graph().edge(bound[i], v))


    def push_out_paulis(self, quiet : bool = True, step : int = 0) -> None:
        """
        Conjugate out Pauli operators from the graph state. After this operation, all state vertices will have phase 0 or 1/2.
        """

        if not quiet:
            print("Start conjugating out:...")

        for v in self._states:
            bound = self.get_bound(v)
            edge = self.get_graph().edge(bound, v)
            edge_type = self.get_graph().edge_type(edge)
            a = self.get_graph().phase(v)
            # row = self.get_graph().row(bound) - 1

            if a != 0 and a != Fraction(1, 2):
                if not quiet:
                    print(f"Step {step}: {self.steps.get(step,'UNKNOWN')} --- Exctracting Pauli operators for vertex {v}, phase {a}")
                if self._paulis is None:
                    self._paulis = {}
                if edge_type == EdgeType.HADAMARD:
                    pauli = self.Pauli(0,1,0)  # X
                else:
                    pauli = self.Pauli(0,0,1)  # Z

                if v not in self._paulis:
                    self._paulis[v] = pauli
                else:
                    self._paulis[v] = self._paulis[v] * pauli

                self.add_to_phase(v, -1)

        if not quiet:
            print(f"Step {step}: {self.steps.get(step,'UNKNOWN')} --- Paulis: {self._paulis}")

        if not self.validate(quiet=quiet, step = step):
            raise ValueError("Graph is not a valid graph state")

    def normalize_graph_state(self, quiet : bool = True) -> None:
        """
        Normalize the graph state by setting proper qubit and row assignments.
        
        Raises:
            ValueError: If the graph is not a valid graph state
        """
        if not self.validate(quiet=quiet):
            raise ValueError("Graph is not a valid graph state")
        
        self.normalize()

        states = self.get_states()
        states.sort()
        
        for i in range(len(states)):
            self.get_graph().set_qubit(self._states[i], i)
            self.get_graph().set_row(self._states[i], (i % 2) * 4)
            bound = self.get_bound(self._states[i])
            self.get_graph().set_qubit(bound, i)
            self.get_graph().set_row(bound, 10)

    def conjugate_in_paulis(self, quiet : bool = True) -> None:
        """
        Conjugate in Pauli operators to the graph state.
        
        Raises:
            ValueError: If a non-Pauli vertex is encountered that should be conjugated in
        """

          
        states = self.get_states()
        g = self.get_graph()

        if not quiet:
            print("Start conjugating out:...")

        for v in states:
            pauli = self._paulis.get(v, self.Pauli(0,0,0))
            bound = self.get_bound(v)
            edge = g.edge(v, bound)
            edge_type = g.edge_type(edge)
            if not quiet:
                print(f"Step {4}: {self.steps.get(4,'UNKNOWN')} --- Injecting Pauli operators {pauli} for vertex {v}")

            if ((edge_type == EdgeType.HADAMARD) and pauli.b == 1) or ((edge_type == EdgeType.SIMPLE) and pauli.c == 1):  # Z case
                g.add_to_phase(v, 1)
            
            if ((edge_type == EdgeType.HADAMARD) and pauli.c == 1) or ((edge_type == EdgeType.SIMPLE) and pauli.b == 1): # X case
                for x in states:
                    if x in g.neighbors(v):
                        g.add_to_phase(x, 1)
        
        if not self.validate(quiet=quiet, step = 4):
            raise ValueError("Graph is not a valid graph state")

        if not self.validate(quiet=quiet, step = 4):
            raise ValueError("Graph is not a valid graph state")     


    def state_to_circuit(self, quiet : bool = True) -> None:
        """
        Convert graph state to circuit representation by setting qubit and row positions.
        """
        ins = list(self.get_graph().inputs())

        input_states = self.get_inputs()
        output_states = self.get_outputs()

        input_states.sort()
        output_states.sort()

        for i in range(len(input_states)):
            self.get_graph().set_qubit(input_states[i], i)
            self.get_graph().set_row(input_states[i], 3)

            bound = self.get_bound(input_states[i])
            self.get_graph().set_qubit(bound, i)
            self.get_graph().set_row(bound, 0)

        for i in range(len(output_states)):
            self.get_graph().set_qubit(output_states[i], i)
            self.get_graph().set_row(output_states[i], 6)

            bound = self.get_bound(output_states[i])
            self.get_graph().set_qubit(bound, i)
            self.get_graph().set_row(bound, 8)

        self.validate(quiet=quiet, step=5)

    def remove_unitaries_input(self, quiet : bool = True) -> None:
        """
        Remove unitary operations from input vertices.
        """
        ins = self.get_graph().inputs()
        for v in self._states:
            bound = self.get_bound(v)
            if bound in ins:
                self.get_graph().set_phase(v, 0)
                e = self.get_graph().edge(v, bound)
                self.get_graph().set_edge_type(e, EdgeType.SIMPLE)

        for e in self.get_graph().edge_set():
            v = self.get_graph().edge_s(e)
            w = self.get_graph().edge_t(e)
            if v in self._states and w in self._states:
                b1 = self.get_bound(v)
                b2 = self.get_bound(w)
                if b1 in ins and b2 in ins:
                    self.get_graph().remove_edge(e)

        if not quiet:
            print(f"Step: {self.steps.get(6,'UNKNOWN')} --- Removed unitaries from inputs")

        if not self.validate(quiet=quiet, step = 6):
            raise ValueError("Graph is not a valid graph state")


    def remove_HS(self, quiet: bool = True) -> None:
        """
        Remove all HS local Clifford operations from the graph state.
        
        Args:
            quiet: If False, display intermediate steps
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
        
        print(f"Step 2: {self.steps.get(2,'UNKNOWN')} --- Removing HS from graph ended:")

        if not self.validate(quiet=quiet, step=2):
            raise ValueError("Graph is not a valid graph state")


    def reorder_H(self, quiet: bool = True) -> None:
        """
        Apply a pivoting strategy to reorder Hadamard edges in the graph state to satisfy the canonical ordering conditions.
     
        Args:
            quiet: If False, display intermediate steps and print pivot operations
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
                            self.pivot(y, x, quiet = quiet, step=3)
                            # edge = self.get_graph().edge(y, self.get_bound(y))
                            # if self.get_graph().phase(y) == Fraction(1, 2) and self.get_graph().edge_type(edge) == EdgeType.HADAMARD: 
                            #     self.local_comp_SH(y, quiet= quiet, step = 3)
                            go_on = True
                            # self.push_out_paulis()
                            break
        
        if not self.validate(quiet=quiet, step = 3):
            raise ValueError("Graph is not a valid graph state")

    def remove_pivot_phases(self, quiet : bool = True) -> None:
        """
        Remove local complementation pivot operations.
        
        Args:
            pivots: List of pivot vertices
        """

        pivots = self.get_pivots()

        if not quiet:
            print(f"Step {8}: {self.steps.get(8,'UNKNOWN')} --- Removing pivot phases for pivots: {pivots}")

        go_on = True
        while go_on:
            go_on = False
            for v in pivots:
                if self.get_graph().phase(v) != 0:
                    neighbors = [x for x in self.get_graph().neighbors(v) if x in self._states]
                    inputs_states = self.get_inputs()
                    vin = -1
                    for x in neighbors:
                        if x in inputs_states:
                            vin = x

                    if not quiet:
                        print(f"Step {8}: {self.steps.get(8,'UNKNOWN')} --- Removing pivot phase for vertex {vin} with phase {self.get_graph().phase(v)}")
                    # self.get_graph().set_phase(vin, 0)
                    neighborsin = [x for x in self.get_graph().neighbors(vin) if x in self.get_outputs()]
                    for x in neighborsin:
                        self.get_graph().add_to_phase(x, Fraction(1, 2))

                    go_on = True
                    break
        
        if not self.validate(quiet=quiet, step = 8):
            raise ValueError("Graph is not a valid graph state")

    def to_RRREF(self, quiet : bool = True) -> List[VT]:
        """
        Transform the graph state to a reduced row echelon form.
        
        Returns:
            List of pivot vertices
        """
        ins = [x for x in self._states if self.get_bound(x) in self.get_graph().inputs()]
        outs = [x for x in self._states if self.get_bound(x) in self.get_graph().outputs()]

        mat = bi_adj(self.get_graph(), ins, outs)
        mat = mat.transpose()

        if not quiet:
            print(f"Step {7}: {self.steps.get(7,'UNKNOWN')} --- Reducing the matrix to RREF:")
            print(mat)
            print(">>>>>>>>>")

        mat.gauss(full_reduce=True)
        pivots = []
        for i in range(mat.rows()):
            for j in range(mat.cols()):
                if mat[i, j] != 0:
                    pivots.append(j)
                    break

        pivots = [outs[j] for j in pivots]
        if not quiet:
            print(mat)
        mat = mat.transpose()

        connectivity_from_biadj(self.get_graph(), mat, ins, outs)

        self._pivots = pivots
        if not quiet:
            print(f"Step {7}: {self.steps.get(7,'UNKNOWN')} --- PIVOTS: {pivots}")

        if not self.validate(quiet=quiet, step = 7):
            raise ValueError("Graph is not a valid graph state")
      
        return pivots

    def remove_pivot_edges(self, quiet : bool = True) -> None:
        """
        Remove edges between pivot vertices.
        
        Args:
            pivots: List of pivot vertices
        """

        pivots = self.get_pivots()

        for x in pivots:
            for y in pivots:
                if x != y and self.get_graph().connected(x, y):
                    if not quiet:
                        print(f"Step {9}: {self.steps.get(9,'UNKNOWN')} --- Removing pivot-pivot edges from pivots: {pivots}")
                    # self.getget_graph()().remove_edge(self.getget_graph()().edge(x, y))
                    self.pivot(x, y, quiet = quiet, step=9)

        if not self.validate(quiet=quiet, step = 9):
            raise ValueError("Graph is not a valid graph state")


    #TODO: Vertify Canonical form


    def validate_canonical_form(self, quiet : bool = True) -> bool:
        return False

    def to_canonical_form(self, quiet : bool = True):

        """
        Reduce the extended graph state to its canonical form.

        Args:
            quiet: If False, display intermediate steps and print pivot operations
        """     
        print(f"STARTING: CANONICAL FORM")
        print()

        if not self.validate(quiet = quiet, step=0):
            raise ValueError("Graph is not a valid graph state")
        
        print(f"Step {1}: {self.steps.get(1,'UNKNOWN')}")
        # self.push_out_paulis(quiet=quiet, step = 1) # O(n)
        print(f"Step {2}: {self.steps.get(2,'UNKNOWN')}")
        self.remove_HS(quiet=quiet)
        print(f"Step {3}: {self.steps.get(3,'UNKNOWN')}")
        self.reorder_H(quiet = quiet)
        print(f"Step {4}: {self.steps.get(4,'UNKNOWN')}")
        # self.conjugate_in_paulis(quiet= quiet)

        print("---------------------------------")
        print("OUTPUT:...................")
        if not self.validate(quiet = quiet, step=0):
            raise ValueError("Graph is not a valid graph state")

    def export_universal_circuit(self, quiet : bool = True) -> BaseGraph:
        """        
        Export the graph state to a universal graph representation.

        Returns:
            A BaseGrpah object representing the universal circuit
        """
        ## Here start steps for the second canonical form

        #TODO Ensure we are in graph state canonical form

        if not self.validate_canonical_form(quiet = quiet):
            self.to_canonical_form(quiet = quiet)

        print("Exporting to universal circuit...")
        print(f"Step {5}: {self.steps.get(5,'UNKNOWN')}")
        self.state_to_circuit(quiet = quiet)
        print(f"Step {7}: {self.steps.get(7,'UNKNOWN')}")
        self.to_RRREF(quiet = quiet)
        print(f"Step {8}: {self.steps.get(8,'UNKNOWN')}")
        self.remove_pivot_phases(quiet = True)
        print(f"Step {9}: {self.steps.get(9,'UNKNOWN')}")
        self.remove_pivot_edges(quiet = True)
        print(f"Step {6}: {self.steps.get(6,'UNKNOWN')}")
        self.remove_unitaries_input(quiet = quiet)

        return self.get_graph()



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

