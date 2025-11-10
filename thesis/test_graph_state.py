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
from pyzx import draw
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

    def setUp(self):
        self.reset = True
        self.n = 8
        self.k = 1
        self.num_subtseps = 20
    
    def stim_qasm_comply(self, qasm: str) -> str:
        q = qasm
        q = re.sub(r'def\s+rx\(qubit q0\)\s*\{[^}]*\}\n+', '', q)
        q = re.sub(r'rx\s*\(\s*q\[(\d+)\]\s*\)\s*;', r'h q[\1];', q)
        # q = re.sub(r'rx\s*\(\s*q\[(\d+)\]\s*\)\s*;', '', q)
        q = re.sub(r'reset\s+q\[(\d+)\];', '', q)
        return q
    

    def test_graph_state(self):
        for i in range(0,self.num_subtseps):
            with self.subTest(i=i):
                s = f"test_{i}"
                print(f"Testing graph state for {s}")
                tableau = stim.Tableau.random(self.n)

                qasm_random1 = tableau.to_circuit(method = "elimination").to_qasm(open_qasm_version=3)
                pyzx_circ1 = Circuit.from_qasm(qasm_random1)
                g1 = pyzx_circ1.to_graph()
                input_state = "0"*(self.n-self.k) + "/"*self.k
                g1.apply_state(input_state)
                g1 = GraphState(g1)
                g1.to_canonical_form()

                t1 = tensorfy(g1)

                n = self.n 
                k = self.k
            
                stabilizers = []

                for i in range (n - k):
                    stabilizers.append(stim.PauliString(f"Z{i}") * stim.PauliString(n+k))

                for i in range(n-k, n): 
                    stabilizers.append(stim.PauliString(f"Z{i}*Z{i+k}") * stim.PauliString(n+k)) 
                    stabilizers.append(stim.PauliString(f"X{i}*X{i+k}") * stim.PauliString(n+k)) 


                state = stim.TableauSimulator()
                state.set_state_from_stabilizers(stabilizers)
                state.do_tableau(tableau, range(n))
                t = state.current_inverse_tableau().inverse()

                qasm_random2 = t.to_circuit(method="graph_state").to_qasm(open_qasm_version=3)       
                pyzx_circ2 = Circuit.from_qasm(self.stim_qasm_comply(qasm_random2))
                g2 = pyzx_circ2.to_graph()
                input_state = "0"*(n+k)
                g2.apply_state(input_state)
                g2 = GraphState(g2)
                g2.to_canonical_form()
                t2 = tensorfy(g2)
                self.assertTrue(compare_tensors(t1, t2, preserve_scalar=False), f"Graph state failed for {i}")
    
    @unittest.skip("Skipping canonical form test for now")
    def test_extraction(self):
        for i in range(0,self.num_subtseps):
            with self.subTest(i=i):
                s = f"test_{i}"
                print(f"Testing extraction for {s}")
                tableau = stim.Tableau.random(self.n)
                qasm_random1 = tableau.to_circuit(method = "elimination").to_qasm(open_qasm_version=3)
                qasm_random2 = tableau.to_circuit(method = "graph_state").to_qasm(open_qasm_version=3)
                # print(self.stim_qasm_comply(qasm_random2))
                pyzx_circ1 = Circuit.from_qasm(qasm_random1)
                pyzx_circ2 = Circuit.from_qasm(self.stim_qasm_comply(qasm_random2))
                # draw(pyzx_circ2.to_graph(), labels=True)

                

                g1 = pyzx_circ1.to_graph()
                g2 = pyzx_circ2.to_graph()
                input_state = "0"*(self.n)
                # input_state = "0"*(self.n-self.k) + "/"*self.k
                g1.apply_state(input_state)
                g2.apply_state(input_state)

                t1 = tensorfy(g1)
                t2 = tensorfy(g2)
                  # print(t2)
                self.assertTrue(compare_tensors(t1, t2), f"Extraction failed for {i}")
    
    # @unittest.skip("Skipping canonical form test for now")
    def test_canonical_form(self):
    
        for i in range(0,self.num_subtseps):
            with self.subTest(i=i):
                s = f"test_{i}"
                file_path = f"./test_graphs/{s}.qasm"
                if not os.path.exists(file_path) or self.reset == True:
                    qasm_random = stim.Tableau.random(self.n).to_circuit(method = "elimination").to_qasm(open_qasm_version=3)
                    # qasm_random = self.stim_qasm_comply(qasm_random)
                    with open(file_path, "w") as f:
                        f.write(qasm_random)
                print(f"Testing canonical form for {s}")
                file_path = f"./test_graphs/{s}.qasm"
                with open(file_path, "r") as f:
                    qasm_random = f.read()
                pyzx_circ = Circuit.from_qasm(qasm_random)
                g = pyzx_circ.to_graph()
                input_state = "0"*(self.n-self.k) + "/"*self.k
                g.apply_state(input_state)
                # draw(g) 
                g = GraphState(g)
                t1 = tensorfy(g)
                # draw(g, labels=True)
                g.to_canonical_form(quiet=True)
                # draw(g) 
                # g = g.state_to_map()
                # clifford_simp(g, quiet=True) # O(n)
                t2 = tensorfy(g)
                # print(t1)
                # print(t2)
                self.assertTrue(compare_tensors(t1, t2), f"Canonical form failed for {i}")


if __name__ == '__main__':
    unittest.main()
