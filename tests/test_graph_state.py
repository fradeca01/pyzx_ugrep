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


NUM_RANDOM_CASES = 10
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


def graph_from_UGR(ugr):
    graph = Graph()
    input_set = set(ugr.inputs)
    internal_vertices = []
    boundary_vertices = []

    for vertex in range(len(ugr.adj)):
        local_clifford = ugr.local_cliffords.get(vertex, "")
        is_input = vertex in input_set
        qubit = vertex if is_input else vertex - len(ugr.inputs)
        internal = graph.add_vertex(VertexType.Z, phase=LOCAL_CLIFFORD_PHASES[local_clifford])
        boundary = graph.add_vertex(VertexType.BOUNDARY)
        edge_type = EdgeType.HADAMARD if local_clifford.startswith("H") else EdgeType.SIMPLE

        graph.set_qubit(internal, qubit)
        graph.set_qubit(boundary, qubit)
        graph.set_row(boundary, 0 if is_input else 3)
        graph.set_row(internal, 1 if is_input else 2)
        graph.add_edge((boundary, internal), edge_type)

        internal_vertices.append(internal)
        boundary_vertices.append(boundary)

    for vertex, neighbors in enumerate(ugr.adj):
        for neighbor in neighbors:
            if vertex < neighbor:
                graph.add_edge((internal_vertices[vertex], internal_vertices[neighbor]), EdgeType.HADAMARD)

    graph.set_inputs(tuple(boundary_vertices[vertex] for vertex in ugr.inputs))
    graph.set_outputs(tuple(boundary_vertices[vertex] for vertex in range(len(ugr.adj)) if vertex not in input_set))
    return graph


def encoder_graph_from_UGR(ugr):
    circuit = implement_encoder(ugr)
    graph = circuit.to_graph()
    original_inputs = list(graph.inputs())
    k = len(ugr.inputs)
    pivot_for_input = dict(zip(ugr.inputs, ugr.pivots))
    pivot_qubits = {pivot - k for pivot in pivot_for_input.values()}
    input_state = "".join("/" if qubit in pivot_qubits else "0" for qubit in range(circuit.qubits))

    graph.apply_state(input_state)
    graph.set_inputs(tuple(original_inputs[pivot_for_input[input_vertex] - k] for input_vertex in ugr.inputs))
    return graph


def pyzx_circuit_to_stim(circuit: Circuit) -> "stim.Circuit":
    stim_circuit = stim.Circuit()

    for gate in circuit.gates:
        gate_name = type(gate).__name__
        if gate_name == "HAD":
            stim_circuit.append("H", [gate.target])
        elif gate_name == "CZ":
            stim_circuit.append("CZ", [gate.control, gate.target])
        elif gate_name == "S":
            stim_circuit.append("S_DAG" if gate.adjoint else "S", [gate.target])
        elif gate_name == "Z":
            stim_circuit.append("Z", [gate.target])
        else:
            raise ValueError(f"Unsupported PyZX gate emitted by implement_encoder: {gate}")

    return stim_circuit


def implemented_encoder_stabilizers(ugr) -> list["stim.PauliString"]:
    circuit = implement_encoder(ugr)
    tableau = stim.Tableau.from_circuit(pyzx_circuit_to_stim(circuit))
    k = len(ugr.inputs)
    pivot_qubits = {pivot - k for pivot in ugr.pivots}
    stabilizers = []

    for qubit in range(circuit.qubits):
        if qubit not in pivot_qubits:
            ancilla_stabilizer = stim.PauliString(circuit.qubits)
            ancilla_stabilizer[qubit] = "Z"
            stabilizers.append(tableau(ancilla_stabilizer))

    return stabilizers


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
        actual_stabilizers = to_stabilizer_tableau(actual_ugr)

        # expected_graph = stabilizers_to_ZX_graph(stabilizers)
        # expected_zxcf = graph_to_ZXCF(expected_graph)
        # ugr_graph = graph_from_UGR(actual_ugr)

        failure_context = (
            f"Stabilizers:\n{canonical_stabilizer_group(stabilizers)}\n"
        )

        # self.assertEqual(len(actual_ugr.adj), n + k, f"UGR has the wrong number of graph nodes\n{failure_context}")
        # self.assertTrue(
        #     compare_tensors(tensorfy(ugr_graph), tensorfy(expected_zxcf.graph)),
        #     f"UGR does not represent an encoder for the same code\n{failure_context}",
        # )
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

    def test_universal_representation(self):
        for case_idx in range(NUM_RANDOM_CASES):
            with self.subTest(case_idx=case_idx):
                tableau = stim.Tableau.random(N_QUBITS)
                self.assert_UGR(tableau, N_QUBITS, K_QUBITS)


if __name__ == "__main__":
    unittest.main()
