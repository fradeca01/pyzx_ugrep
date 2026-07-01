from fractions import Fraction
import re
import unittest

try:
    import stim
    from pyzx.graph import Graph
    from pyzx.circuit import Circuit
    from pyzx.tensor import compare_tensors, tensorfy
    from pyzx.utils import EdgeType, VertexType

    from ugr import GraphState, ZXCF_to_UGR, graph_to_ZXCF, implement_encoder, stabilizers_to_UGR, stabilizers_to_ZX_graph, to_stabilizer_tableau
except ImportError as exc:
    raise unittest.SkipTest("stim, pyzx, and package dependencies need to be installed for this to run") from exc


NUM_RANDOM_CASES = 20
N_QUBITS = 7
K_QUBITS = 3

LOCAL_CLIFFORD_PHASES = {
    "": 0,
    "S": Fraction(1, 2),
    "Z": 1,
    "SZ": Fraction(3, 2),
    "H": 0,
    "HZ": 1,
}


def stim_qasm_comply(qasm: str) -> str:
    q = qasm
    q = re.sub(r'def\s+rx\(qubit q0\)\s*\{[^}]*\}\n+', '', q)
    q = re.sub(r'rx\s*\(\s*q\[(\d+)\]\s*\)\s*;', r'h q[\1];', q)
    q = re.sub(r'reset\s+q\[(\d+)\];', '', q)
    return q

def graph_state_from_tableau(tableau: "stim.Tableau", n: int, k: int):
    stabilizers = []

    for qubit in range(k, n):
        stabilizers.append(stim.PauliString(f"Z{qubit}") * stim.PauliString(n + k))

    for qubit in range(k):
        stabilizers.append(stim.PauliString(f"Z{qubit}*Z{qubit + n}") * stim.PauliString(n + k))
        stabilizers.append(stim.PauliString(f"X{qubit}*X{qubit + n}") * stim.PauliString(n + k))

    state = stim.TableauSimulator()
    state.set_state_from_stabilizers(stabilizers)
    state.do_tableau(tableau, list(range(k, n + k)))
    graph_state_tableau = state.current_inverse_tableau().inverse()
    qasm = graph_state_tableau.to_circuit(method="graph_state").to_qasm(open_qasm_version=3)
    pyzx_circ = Circuit.from_qasm(stim_qasm_comply(qasm))
    graph = pyzx_circ.to_graph()
    graph.apply_state("0" * (n + k))
    graph.set_inputs(graph.outputs()[0:k])
    return graph, qasm


def elimination_graph_from_tableau(tableau: "stim.Tableau", n: int, k: int):
    qasm = tableau.to_circuit(method="elimination").to_qasm(open_qasm_version=3)
    pyzx_circ = Circuit.from_qasm(qasm)
    graph = pyzx_circ.to_graph()
    graph.apply_state("0" * (n - k) + "/" * k)
    return graph


def code_stabilizers_from_tableau(tableau: "stim.Tableau", n: int, k: int) -> list[str]:
    return [str(stabilizer) for stabilizer in tableau.to_stabilizers()[0 : n - k]]


def canonical_stabilizer_group(stabilizers) -> tuple[str, ...]:
    pauli_stabilizers = [
        stim.PauliString(stabilizer) for stabilizer in stabilizers
    ]
    group = {str(stim.PauliString(len(pauli_stabilizers[0])))}

    for stabilizer in pauli_stabilizers:
        group.update(str(stim.PauliString(element) * stabilizer) for element in tuple(group))

    return tuple(sorted(group))


def deterministic_code_tableaus(n: int) -> list[tuple[str, "stim.Tableau"]]:
    identity = stim.Tableau(n)

    hadamard_layer = stim.Circuit()
    phase_layer = stim.Circuit()
    alternating_layer = stim.Circuit()
    chain = stim.Circuit()
    reverse_chain = stim.Circuit()
    star = stim.Circuit()

    for qubit in range(n):
        hadamard_layer.append("H", [qubit])
        phase_layer.append("S", [qubit])
        if qubit % 2 == 0:
            alternating_layer.append("H", [qubit])
        else:
            alternating_layer.append("S", [qubit])

    for qubit in range(n - 1):
        chain.append("CX", [qubit, qubit + 1])
        reverse_chain.append("CX", [n - qubit - 1, n - qubit - 2])

    star.append("H", [0])
    for qubit in range(1, n):
        star.append("CX", [0, qubit])

    return [
        ("identity", identity),
        ("hadamard_layer", stim.Tableau.from_circuit(hadamard_layer)),
        ("phase_layer", stim.Tableau.from_circuit(phase_layer)),
        ("alternating_h_s_layer", stim.Tableau.from_circuit(alternating_layer)),
        ("cx_chain", stim.Tableau.from_circuit(chain)),
        ("reverse_cx_chain", stim.Tableau.from_circuit(reverse_chain)),
        ("star_entangler", stim.Tableau.from_circuit(star)),
    ]


class TestGraphState(unittest.TestCase):
    def assert_UGR_properties(self, ugr, n, k, failure_context):
        vertex_set = set(range(len(ugr.adj)))
        input_set = set(ugr.inputs)
        pivot_set = set(ugr.pivots)
        output_set = vertex_set - input_set

        self.assertEqual(n + k, len(ugr.adj), f"UGR has the wrong number of nodes\n{failure_context}")
        self.assertEqual(k, len(ugr.inputs), f"UGR has the wrong number of inputs\n{failure_context}")
        self.assertEqual(k, len(ugr.pivots), f"UGR has the wrong number of pivots\n{failure_context}")
        self.assertEqual(n, len(output_set), f"UGR has the wrong number of outputs\n{failure_context}")

        self.assertEqual(len(ugr.inputs), len(input_set), f"UGR inputs are not distinct\n{failure_context}")
        self.assertEqual(len(ugr.pivots), len(pivot_set), f"UGR pivots are not distinct\n{failure_context}")
        self.assertTrue(pivot_set <= output_set, f"UGR pivots must be output vertices\n{failure_context}")

        for vertex, neighbors in enumerate(ugr.adj):
            neighbor_set = set(neighbors)
            self.assertEqual(
                len(neighbors),
                len(neighbor_set),
                f"UGR adjacency list has duplicate edges at vertex {vertex}\n{failure_context}",
            )
            self.assertNotIn(vertex, neighbor_set, f"UGR has a self-loop at vertex {vertex}\n{failure_context}")
            self.assertTrue(
                neighbor_set <= vertex_set,
                f"UGR vertex {vertex} has neighbors outside the graph: {neighbor_set - vertex_set}\n{failure_context}",
            )
            for neighbor in neighbors:
                self.assertIn(
                    vertex,
                    ugr.adj[neighbor],
                    f"UGR edge ({vertex}, {neighbor}) is not symmetric\n{failure_context}",
                )

        input_edges = [
            (x, y)
            for x in ugr.inputs
            for y in ugr.adj[x]
            if y in input_set and x < y
        ]
        self.assertEqual([], input_edges, f"UGR has input-input edges\n{failure_context}")

        pivot_edges = [
            (x, y)
            for x in ugr.pivots
            for y in ugr.adj[x]
            if y in pivot_set and x < y
        ]
        self.assertEqual([], pivot_edges, f"UGR has pivot-pivot edges\n{failure_context}")

        expected_input_pivots = {input_vertex: [pivot] for input_vertex, pivot in zip(ugr.inputs, ugr.pivots)}
        actual_input_pivots = {
            input_vertex: sorted(neighbor for neighbor in ugr.adj[input_vertex] if neighbor in pivot_set)
            for input_vertex in ugr.inputs
        }
        self.assertEqual(
            expected_input_pivots,
            actual_input_pivots,
            f"UGR inputs are not matched to their declared pivots\n{failure_context}",
        )

        expected_pivot_inputs = {pivot: [input_vertex] for input_vertex, pivot in zip(ugr.inputs, ugr.pivots)}
        actual_pivot_inputs = {
            pivot: sorted(neighbor for neighbor in ugr.adj[pivot] if neighbor in input_set)
            for pivot in ugr.pivots
        }
        self.assertEqual(
            expected_pivot_inputs,
            actual_pivot_inputs,
            f"UGR pivots are not matched to exactly one declared input\n{failure_context}",
        )

        outputs = [vertex for vertex in range(len(ugr.adj)) if vertex not in input_set]
        partial_adjacency = [
            [int(output in ugr.adj[input_vertex]) for output in outputs]
            for input_vertex in ugr.inputs
        ]
        pivot_columns = []
        seen_zero_row = False
        rref_violations = []

        for row_index, row in enumerate(partial_adjacency):
            nonzero_columns = [column for column, value in enumerate(row) if value]
            if not nonzero_columns:
                seen_zero_row = True
                continue
            if seen_zero_row:
                rref_violations.append(f"nonzero row {row_index} appears after a zero row")

            pivot_column = nonzero_columns[0]
            if pivot_columns and pivot_column <= pivot_columns[-1]:
                rref_violations.append(
                    f"pivot column {pivot_column} is not to the right of previous pivot {pivot_columns[-1]}"
                )

            for other_row_index, other_row in enumerate(partial_adjacency):
                if other_row_index != row_index and other_row[pivot_column]:
                    rref_violations.append(
                        f"pivot column {pivot_column} has a nonzero entry in row {other_row_index}"
                    )

            pivot_columns.append(pivot_column)

        self.assertEqual([], rref_violations, f"UGR partial adjacency is not in RREF\n{failure_context}")
        self.assertEqual(
            [outputs.index(pivot) for pivot in ugr.pivots],
            pivot_columns,
            f"UGR declared pivots are not the RREF pivot columns\n{failure_context}",
        )

        local_clifford_vertices = set(ugr.local_cliffords)
        self.assertTrue(
            local_clifford_vertices <= vertex_set,
            f"UGR local Clifford map references invalid vertices\n{failure_context}",
        )

        invalid_local_cliffords = {
            vertex: local_clifford
            for vertex, local_clifford in ugr.local_cliffords.items()
            if local_clifford not in LOCAL_CLIFFORD_PHASES
        }
        self.assertEqual(
            {},
            invalid_local_cliffords,
            f"UGR has local Cliffords outside the paper's allowed set\n{failure_context}",
        )

        input_or_pivot_local_cliffords = {
            vertex: ugr.local_cliffords.get(vertex, "")
            for vertex in input_set | pivot_set
            if ugr.local_cliffords.get(vertex, "") != ""
        }
        self.assertEqual(
            {},
            input_or_pivot_local_cliffords,
            f"UGR has local Clifford operations on inputs or pivots\n{failure_context}",
        )

        hadamard_rule_violations = []
        for output in output_set:
            local_clifford = ugr.local_cliffords.get(output, "")
            if not local_clifford.startswith("H"):
                continue

            forbidden_neighbors = sorted(
                neighbor
                for neighbor in ugr.adj[output]
                if neighbor in input_set or (neighbor in output_set and neighbor < output)
            )
            if forbidden_neighbors:
                hadamard_rule_violations.append((output, local_clifford, forbidden_neighbors))

        self.assertEqual(
            [],
            hadamard_rule_violations,
            f"UGR violates the Hadamard rule\n{failure_context}",
        )

    def assert_canonical_form(self, tableau, n, k):
        graph_state_graph, graph_state_qasm = graph_state_from_tableau(tableau, n, k)
        graph = GraphState(graph_state_graph)
        before = tensorfy(graph.get_graph())

        graph.to_canonical_form(quiet=True)
        after = tensorfy(graph.get_graph())

        failure_context = (
            "Graph-state QASM generated from code tableau:\n"
            f"{graph_state_qasm}"
        )
        self.assertTrue(compare_tensors(before, after), f"Canonicalization changed the tensor\n{failure_context}")
        self.assertTrue(graph.validate_canonical_form(), f"Canonicalized graph is not in canonical form\n{failure_context}")

    def assert_graph_state_synthesis(self, tableau, n, k):
        graph_state_graph, graph_state_qasm = graph_state_from_tableau(tableau, n, k)
        elimination_graph = elimination_graph_from_tableau(tableau, n, k)

        graph_state_zxcf = graph_to_ZXCF(graph_state_graph).graph
        elimination_zxcf = graph_to_ZXCF(elimination_graph).graph

        failure_context = (
            "Graph-state QASM generated from code tableau:\n"
            f"{graph_state_qasm}"
        )
        self.assertTrue(
            compare_tensors(tensorfy(graph_state_zxcf), tensorfy(elimination_zxcf)),
            f"Graph-state synthesis does not match elimination synthesis\n{failure_context}",
        )

    def assert_UGR(self, tableau, n, k):
        stabilizers = code_stabilizers_from_tableau(tableau, n, k)

        actual_ugr = stabilizers_to_UGR(stabilizers)

        failure_context = (
            f"Stabilizers:\n{(stabilizers)}\n"
        )

        self.assert_UGR_properties(actual_ugr, n, k, failure_context)

        actual_stabilizers = to_stabilizer_tableau(actual_ugr)
        self.assertEqual(
            canonical_stabilizer_group(stabilizers),
            canonical_stabilizer_group(actual_stabilizers),
            f"UGR stabilizer generators do not generate the starting stabilizer group\n"
            f"{failure_context}"
            f"UGR stabilizers:\n{actual_stabilizers}",
        )


    def test_deterministic_canonical(self):
        for case_name, tableau in deterministic_code_tableaus(N_QUBITS):
            with self.subTest(case_name=case_name):
                self.assert_canonical_form(tableau, N_QUBITS, K_QUBITS)

    def test_random_code_canonical(self):
        for case_idx in range(NUM_RANDOM_CASES):
            with self.subTest(case_idx=case_idx):
                tableau = stim.Tableau.random(N_QUBITS)
                self.assert_canonical_form(tableau, N_QUBITS, K_QUBITS)

    def test_graph_state_synthesis(self):
        for case_idx in range(NUM_RANDOM_CASES):
            with self.subTest(case_idx=case_idx):
                tableau = stim.Tableau.random(N_QUBITS)
                self.assert_graph_state_synthesis(tableau, N_QUBITS, K_QUBITS)


if __name__ == "__main__":
    unittest.main()
