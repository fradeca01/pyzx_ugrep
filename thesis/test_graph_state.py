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
        reset = True
        self.n = 7
        self.k = 1
        self.num_subtseps = 10
    
        for i in range(self.num_subtseps):
            s = f"test_{i}"
            file_path = f"./test_graphs/{s}.qasm"
            if not os.path.exists(file_path) or reset == True:
                qasm_random = stim.Tableau.random(self.n).to_circuit(method = "elimination").to_qasm(open_qasm_version=3)
                # qasm_random = self.stim_qasm_comply(qasm_random)
                with open(file_path, "w") as f:
                    f.write(qasm_random)


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
                pyzx_circ = Circuit.from_qasm(qasm_random1)
                g = pyzx_circ.to_graph()
                input_state = "0"*(4) + "/"*1
                g.apply_state(input_state)
                g = GraphState(g)
                g.to_canonical_form()

                t1 = tensorfy(g)

                out = self.n - self.k
                n = self.n
                input = self.k


                stabilizers = []

                for i in range (out - input):
                    stabilizers.append(stim.PauliString(f"Z{i}") * stim.PauliString(n))

                # Loop must go from 0 to N-2
                for i in range(out - input, n-1): 
                    stabilizers.append(stim.PauliString(f"Z{i}*Z{i+1}") * stim.PauliString(n)) 

                stabilizers.append(stim.PauliString("I" * (out - input))  + stim.PauliString("X" * (n - (out - input))))

                # print("Stabilizers:")
                # for s in stabilizers:
                #     print(s)

                tableau = stim.Tableau.from_stabilizers(stabilizers)

                state = stim.TableauSimulator()
                state.set_state_from_stabilizers(stabilizers)
                state.do_tableau(tableau, range(out - input + 1))

                print(state.current_inverse_tableau().inverse())
                t = state.current_inverse_tableau().inverse()

                qasm_random2 = t.to_circuit(method="graph_state").to_qasm(open_qasm_version=3)       
                pyzx_circ = Circuit.from_qasm(self.stim_qasm_comply(qasm_random2))
                g = pyzx_circ.to_graph()
                input_state = "0"*(n)
                g.apply_state(input_state)
                clifford_simp(g)
                g.normalize()
                g.auto_detect_io()
                g = GraphState(g)
                g.to_canonical_form()
                t2 = tensorfy(g)

                self.assertTrue(compare_tensors(t1, t2), f"Graph state failed for {i}")
    
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
    
    @unittest.skip("Skipping canonical form test for now")
    def test_canonical_form(self):
    
        for i in range(0,self.num_subtseps):
            with self.subTest(i=i):
                s = f"test_{i}"
                print(f"Testing canonical form for {s}")
                file_path = f"./test_graphs/{s}.qasm"
                with open(file_path, "r") as f:
                    qasm_random = f.read()
                pyzx_circ = Circuit.from_qasm(qasm_random)
                g = pyzx_circ.to_graph()
                input_state = "0"*(self.n-self.k) + "/"*self.k
                g.apply_state(input_state)
                # draw(g) 
                t1 = tensorfy(g)
                g = GraphState(g)
                # draw(g, labels=True)
                g.to_canonical_form(quiet=True)
                # draw(g) 
                g = g.state_to_map()
                # clifford_simp(g, quiet=True) # O(n)
                t2 = tensorfy(g)
                # print(t1)
                # print(t2)
                self.assertTrue(compare_tensors(t1, t2), f"Canonical form failed for {i}")


if __name__ == '__main__':
    unittest.main()
