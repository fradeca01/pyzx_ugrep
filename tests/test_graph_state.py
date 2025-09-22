import unittest
import random
import sys
import os
from types import ModuleType
from typing import Optional

if __name__ == '__main__':
    sys.path.append('..')
    sys.path.append('.')
mydir = os.path.dirname(__file__)
from pyzx.generate import cliffordT, cliffords
from pyzx.simplify import clifford_simp
from pyzx.extract import extract_circuit
from pyzx.circuit import Circuit
from pyzx.graph import Graph
from pyzx.graph_states import GraphState

np: Optional[ModuleType]
try:
    import numpy as np
    import stim as stim
    import re
    from pyzx.tensor import tensorfy, compare_tensors
    import math
except ImportError:
    np = None
    stim = None

SEED = 1337


@unittest.skipUnless(stim, "stim needs to be installed for this to run")
class TestCircuit(unittest.TestCase):

    def stim_qasm_comply(qasm: str) -> str:
        q = qasm
        q = re.sub(r'def\s+rx\(qubit q0\)\s*\{[^}]*\}\n+', '', q)
        q = re.sub(r'rx\s*\(\s*q\[(\d+)\]\s*\)\s*;', r'h q[\1];', q)
        q = re.sub(r'reset\s+q\[(\d+)\];', '', q)
        return q

    def setUp(self):
        n = 3
        k = 1
        graphs = []
        for i in range(10):
            s = f"test_{i}"
            n = 3 
            k = 2
            file_path = f"./test_graphs/{s}.json"
            graphs.append(Graph.from_json(file_path))

    def test_canonical_form(self):
        n = 3
        k = 1
        for i in range(10):
            s = f"test_{i}"
            n = 3 
            k = 2
            file_path = f"./test_graphs/{s}.qasm"
            with open(file_path, "r") as f:
                qasm_random = f.read()
            pyzx_circ = Circuit.from_qasm(qasm_random)
            g = pyzx_circ.to_graph()
            input_state = "0"*(n-k) + "/"*k
            g.apply_state(input_state)
            g = GraphState(g)
            g.to_canonical_form(quiet=True)

if __name__ == '__main__':
    unittest.main()
