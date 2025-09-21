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
    }

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
        clifford_simp(graph, quiet=False) # O(n)
        # graph.normalize()

        self._graph = graph
        states = [x for x in graph.vertex_set() if graph.types()[x] != VertexType.BOUNDARY]
        self._states = states
        self._pivots = None
        self._paulis = None

        self.fix_free_edges(quiet=True)
        self.normalize_graph_state(quiet=True)

        self.validate()

    # @classmethod
    # def from_clifford_diagram(cls, cliffDiagram : BaseGraph) -> "GraphState":
    #     """, 
    #     Create a GraphState from a Clifford Circuit.
        
    #     Args:
    #         circ: The clifford circuit to convert to a graph state
        
    #     Returns:
    #         A GraphState object
    #     """

    #     #TODO : Check if the diagram is Clifford!!!!

    #     cliffDiagram.auto_detect_io()
    #     # to_graph_like(g) 

    #     #Simplify ZX diagram to be a graph-state
    #     clifford_simp(cliffDiagram, quiet=False) # O(n)
    #     cliffDiagram.normalize()

    #     return cls(cliffDiagram)
    
    def pretty_print(self, draw : bool = False) -> None:
        """
        Print the graph state in a human-readable format.
        """

        print("Graph State:")
        print(f"States: {self._states}")
        print(f"Graph: {self._graph}")
        for i in self.get_states():
            bound = self.get_bound(i)
            print(f"State {i}: Phase = {self._graph.phase(i)}, Type = {self._graph.type(i)}, Bound: {bound}, Type: {self._graph.type(bound)}, Phase: {self._graph.phase(bound)}")

        if draw:
            draw_d3(self._graph, labels=True, scale=65)

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

        g = self._graph

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
            a = self._graph.phase(v) 
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
            print(f"Step {step}: {self.steps.get(step,'UNKNOWN')} --- Graph state is valid:")
            draw_d3(self._graph, labels=True, scale=40)

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
        neighbors = [x for x in self._graph.neighbors(v) if x in self._states]

        a = self.get_graph().phase(v)

        if not (a == 0 and self._graph.edge_type(self._graph.edge(bound, v)) == EdgeType.HADAMARD):
            raise ValueError("This LC must be applied with a pivot ending")

        for x in neighbors:
            self._graph.add_to_phase(x, 1)

        for x in neighbors:
            for y in neighbors:
                if x >= y:
                    continue
                connected = self._graph.connected(x, y)
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
        neighbors = [x for x in self._graph.neighbors(v) if x in self._states]

        if not quiet:
            print(f"Step {step}: {self.steps.get(step,'UNKNOWN')} --- Performing local complementation SH on vertex {v} with bound {bound} and neighbors {neighbors}")

        a = self.get_graph().phase(v)

        if not (a == Fraction(1, 2) and self._graph.edge_type(self._graph.edge(bound, v)) == EdgeType.HADAMARD):
            raise ValueError("This LC must be applied with a SH ending")
        
        self._graph.set_phase(v, 0)

        for x in neighbors:
            self._graph.add_to_phase(x, Fraction(1, 2))

        for x in neighbors:
            for y in neighbors:
                if x >= y:
                    continue
                connected = self._graph.connected(x, y)
                if connected == 0:
                    self._graph.add_edge(edge_pair=(x, y), edgetype=EdgeType.HADAMARD)
                else:
                    self._graph.remove_edge(self._graph.edge(x, y))
        
        self.push_out_paulis(quiet=quiet, step = 3)

        if not self.validate(quiet=True, step = 3):
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
        neighbors = [x for x in self._graph.neighbors(v) if x in self._states]
        a = self._graph.phase(v)
        edge = self.get_graph().edge(bound, v)
        
        if not quiet:
            print(f"Step {2}: {self.steps.get(2,'UNKNOWN')} --- Performing local complementation HS on vertex {v} with bound {bound} and neighbors {neighbors}")

        if not (a % 1 == Fraction(1, 2) and self._graph.edge_type(edge) == EdgeType.HADAMARD):
            raise ValueError("This LC rule must be applied with a HS ending")


        self._graph.add_to_phase(v, -1)
        self._graph.set_edge_type(self._graph.edge(bound, v), EdgeType.SIMPLE)

        # #Xs
        # for x in neighbors:
        #     self._graph.add_to_phase(x, 1)

        #Ss                
        for x in neighbors:
            self._graph.add_to_phase(x, -Fraction(1, 2))

        for x in neighbors:
            for y in neighbors:
                if x >= y:
                    continue
                connected = self._graph.connected(x, y)
                if connected == 0:
                    self._graph.add_edge(edge_pair=(x, y), edgetype=EdgeType.HADAMARD)
                else:
                    self._graph.remove_edge(self._graph.edge(x, y))

        self.push_out_paulis(quiet=quiet, step = 2)

        if not self.validate(quiet=True, step = 2):
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
    
        A = [neighbor for neighbor in self._graph.neighbors(x) if neighbor in self._states] + [x]
        B = [neighbor for neighbor in self._graph.neighbors(y) if neighbor in self._states] + [y]

        edge_x = self._graph.edge(x, self.get_bound(x))
        type_x = self._graph.edge_type(edge_x)
        edge_y = self._graph.edge(y, self.get_bound(y))
        type_y = self._graph.edge_type(edge_y)

        # Flip edge types
        if type_x == EdgeType.SIMPLE:
            type_x = EdgeType.HADAMARD
        else:
            type_x = EdgeType.SIMPLE

        if type_y == EdgeType.SIMPLE:
            type_y = EdgeType.HADAMARD
        else:
            type_y = EdgeType.SIMPLE

        self._graph.set_edge_type(edge_x, type_x)
        self._graph.set_edge_type(edge_y, type_y)


        # PROBABLY WRONGG
        # self._graph.set_phase(x, self._graph.phase(x) + 1)
        # self._graph.set_phase(y, self._graph.phase(y) + 1)

        for v in A:
            if v in B:
                self._graph.add_to_phase(v, 1)

                       # Add/remove edges between A and B sets
        for i in range(len(A)):
            for j in range(len(B)):
                if A[i] == B[j]:
                    continue
                elif not self._graph.connected(A[i], B[j]):
                    self._graph.add_edge((A[i], B[j]), edgetype=EdgeType.HADAMARD)
                else:
                    self._graph.remove_edge(self._graph.edge(A[i], B[j]))

        self.push_out_paulis(quiet=quiet, step = 3)

        if not self.validate(quiet=True, step = step):
            raise ValueError("Graph is not a valid graph state")

    def fix_free_edges(self, quiet : bool = True) -> None:
        """
        Fix input/output connections by ensuring each state vertex has exactly one boundary connection. Add new intermediate state vertices if necessary.
        
        Raises:
            ValueError: If the graph is not graph-like
        """
        if not is_graph_like(self._graph):
            raise ValueError("Graph is not graph-like")

        for v in self._states:
            bound = [x for x in self._graph.neighbors(v) if x not in self._states]
            if len(bound) > 1:
                # print("Vertex:", v, "Phase:", g.phase(v), "Type:", g.types()[v])
                for i in range(len(bound) - 1):
                    edge_type = self._graph.edge_type(self._graph.edge(bound[i], v))
                    new = self._graph.add_vertex(VertexType.Z)
                    self._states.append(new)
                    if edge_type == EdgeType.HADAMARD:
                        self._graph.add_edge((bound[i], new), EdgeType.SIMPLE)
                        # self._graph.add_edge((new, v), EdgeType.HADAMARD)
                    else:
                        self._graph.add_edge((bound[i], new), EdgeType.HADAMARD)

                    self._graph.add_edge((new, v), EdgeType.HADAMARD)
                    self._graph.remove_edge(self._graph.edge(bound[i], v))



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


    def push_out_paulis(self, quiet : bool = True, step : int = 0) -> None:
        """
        Conjugate out Pauli operators from the graph state. After this operation, all state vertices will have phase 0 or 1/2.
        """

        if not quiet:
            print("Start conjugating out:...")

        for v in self._states:
            bound = self.get_bound(v)
            edge = self._graph.edge(bound, v)
            edge_type = self._graph.edge_type(edge)
            a = self._graph.phase(v)
            # row = self._graph.row(bound) - 1

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
        
        for i in range(len(self.get_states())):
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

        if not self.validate(quiet=quiet):
            raise ValueError("Graph is not a valid graph state")     
          
        states = self.get_states()
        g = self.get_graph()

        go_on = True
        while go_on:
            go_on = False
            for v in states:
                bound = self.get_bound(v)
                bound_type = g.type(bound)
                if bound_type != VertexType.BOUNDARY:
                    go_on = True
                    a = g.phase(bound)
                    if not quiet:
                        print(f"Conjugating in vertex {bound} with phase {a} and type {bound_type} for state {v}")
                    if a != 1:
                        raise ValueError(f"Vertex {bound} must be Pauli (phase=1) to conjugate in, but has phase={a}")
                    
                    edge_type = g.edge_type(g.edge(v, bound))
                    if (edge_type == EdgeType.HADAMARD and bound_type == VertexType.X or 
                        edge_type == EdgeType.SIMPLE and bound_type == VertexType.Z):
                        g.add_to_phase(v, 1)
                    elif (edge_type == EdgeType.HADAMARD and bound_type == VertexType.Z or 
                          edge_type == EdgeType.SIMPLE and bound_type == VertexType.X):
                        for x in self._graph.neighbors(v):
                            if x in self._states:
                                g.add_to_phase(x, 1)

                    new_bound = self.get_bound(bound)
                    g.remove_vertex(bound)
                    g.add_edge((v, new_bound), edge_type)
                    break
        

    # DA RIMUOVERE
    def assert_intermediate(self, quiet : bool = True) -> bool:
        """
        Check that after local complementing there is only one LC gate H or S on each state.
        
        Returns:
            True if the intermediate condition is satisfied, False otherwise
        """

        if not self.validate(quiet=quiet):
            raise ValueError("Graph is not a valid graph state")

        for v in self._states:
            edge = self._graph.edge(v, self.get_bound(v))
            if self._graph.phase(v) != 0 and self._graph.edge_type(edge) == EdgeType.HADAMARD:
                return False
        
        return True

    def state_to_circuit(self) -> None:
        """
        Convert graph state to circuit representation by setting qubit and row positions.
        """
        ins = self._graph.inputs()
        print(ins)

        for i in range(len(ins)):
            self._graph.set_qubit(ins[i], i)
            self._graph.set_row(ins[i], 0)

        outs = self.get_graph().outputs()
        for i in range(len(outs)):
            self._graph.set_qubit(outs[i], i)
            self._graph.set_row(outs[i], 8)

        for x in self.get_states():
            bound = self.get_bound(x)
            self.get_graph().set_qubit(x, self._graph.qubit(bound))
            if bound in ins:
                self._graph.set_row(x, 3)
            else: 
                self._graph.set_row(x, 6)

    def remove_unitaries_input(self) -> None:
        """
        Remove unitary operations from input vertices.
        """
        ins = self._graph.inputs()
        for v in self._states:
            bound = self.get_bound(v)
            if bound in ins:
                self._graph.set_phase(v, 0)
                e = self._graph.edge(v, bound)
                self._graph.set_edge_type(e, EdgeType.SIMPLE)

        for e in self._graph.edge_set():
            v = self._graph.edge_s(e)
            w = self._graph.edge_t(e)
            if v in self._states and w in self._states:
                b1 = self.get_bound(v)
                b2 = self.get_bound(w)
                if b1 in ins and b2 in ins:
                    self._graph.remove_edge(e)


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
                phase = self._graph.phase(v)
                edge = self._graph.edge(self.get_bound(v), v)
                edge_type = self._graph.edge_type(edge)
                
                if (phase % 1 == Fraction(1, 2) and edge_type == EdgeType.HADAMARD):
                    self.local_comp_HS(v, quiet=quiet)
                    go_on = True
                    break

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
                    neigh = [v for v in self._graph.neighbors(x) if v in self.get_states()]
                    for y in neigh:
                        if y < x:
                            self.pivot(y, x, quiet = quiet, step=3)
                            edge = self.get_graph().edge(y, self.get_bound(y))
                            if self.get_graph().phase(y) == Fraction(1, 2) and self.get_graph().edge_type(edge) == EdgeType.HADAMARD: 
                                self.local_comp_SH(y, quiet= quiet, step = 3)
                            go_on = True
                            self.push_out_paulis()
                            break
        
        if not self.validate(quiet=quiet, step = 3):
            raise ValueError("Graph is not a valid graph state")

    def remove_pivot_phases(self, pivots: List[VT], quiet : bool = True) -> None:
        """
        Remove local complementation pivot operations.
        
        Args:
            pivots: List of pivot vertices
        """
        go_on = True
        while go_on:
            go_on = False
            for v in pivots:
                if self.get_graph().phase(v) != 0:
                    if not quiet:
                        print(f"Removing pivot phase for vertex {v} with phase {self.get_graph().phase(v)}")
                    self.get_graph().set_phase(v, 0)
                    go_on = True
                    break

    def to_RRREF(self, quiet : bool = True) -> List[VT]:
        """
        Transform the graph state to a reduced row echelon form.
        
        Returns:
            List of pivot vertices
        """
        ins = [x for x in self._states if self.get_bound(x) in self._graph.inputs()]
        outs = [x for x in self._states if self.get_bound(x) in self._graph.outputs()]

        mat = bi_adj(self._graph, ins, outs)
        mat = mat.transpose()

        if not quiet:
            print("Initial bi-adjacency matrix:")
            print(mat)

        mat.gauss(full_reduce=True)
        pivots = []
        for i in range(mat.rows()):
            for j in range(mat.cols()):
                if mat[i, j] != 0:
                    pivots.append(j)
                    break

        pivots = [outs[j] for j in pivots]
        mat = mat.transpose()

        connectivity_from_biadj(self._graph, mat, ins, outs)

        if not quiet:
            print("Reduced bi-adjacency matrix:")
            print(mat)
            draw_d3(self.get_graph(), labels=True, scale=65)
      
        return pivots

    def remove_pivot_edges(self, pivots: List[VT], quiet : bool = True) -> None:
        """
        Remove edges between pivot vertices.
        
        Args:
            pivots: List of pivot vertices
        """
        for x in pivots:
            for y in pivots:
                if x != y and self._graph.connected(x, y):
                    if not quiet:
                        print(f"Removing edge between pivot vertices {x} and {y}")
                    self.get_graph().remove_edge(self.get_graph().edge(x, y))


    #TODO: Vertify Canonical form

    def to_canonical_form(self, quiet : bool = True):

        """
        Reduce the extended graph state to its canonical form.

        Args:
            quiet: If False, display intermediate steps and print pivot operations
        """
        
        # self.fix_free_edges(quiet=quiet) 

        # self.normalize_graph_state(quiet = quiet)


        self.push_out_paulis(quiet=quiet, step = 1) # O(n)
        self.remove_HS(quiet=quiet)
        self.reorder_H(quiet = quiet)
        # self.conjugate_in_paulis(quiet= quiet)


        # The length of each LC is at most 2 and SH is not possible.

        # assert(self.assert_intermediate())





    def export_universal_circuit(self) -> BaseGraph:



        """        
        Export the graph state to a universal graph representation.
        Returns:
            A BaseGrpah object representing the universal circuit
        """
        ## Here start steps for the second canonical form

        #TODO Ensure we are in graph state canonical form
        self.state_to_circuit()
        self.remove_unitaries_input()

        pivots = self.to_RRREF()

        #Just remove the pivot phases
        self.remove_pivot_phases(pivots)

        # Just remove the pivot edges
        self.remove_pivot_edges(pivots)



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

