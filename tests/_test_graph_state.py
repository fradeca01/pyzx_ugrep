import unittest
import sys
from pyzx.circuit import Circuit, cliffords
if __name__ == '__main__':
    sys.path.append('..')
    sys.path.append('.')



class TestGraphState(unittest.TestCase):

    def setUp(self):
        circuit = cliffords(10, 20)
        graph = circuit.to_graph()