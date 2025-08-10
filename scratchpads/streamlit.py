from pyzx import *
import stim
import networkx as nx
from pyvis.network import Network
import streamlit as st

def tableau_to_graph(list, quiet = True):
    n = len(list[0])
    k = n - len(list)
    stabilizers = [stim.PauliString(x) for x in list]
    tableau = stim.Tableau.from_stabilizers(stabilizers, allow_underconstrained=True)
    stim_circ = tableau.to_circuit(method="elimination")
    qasm = stim_circ.to_qasm()
    pyzx_circ = Circuit.from_qasm(qasm)
    g = GraphState.from_circuit(pyzx_circ, k)
    g.to_canonical_form(quiet = quiet)
    return g

def pyzx_graph_to_pyvis(g):
    nxg = nx.Graph()
    for v in g.get_states():
        v_type = g.type(v)
        if g.get_bound(v) in g.inputs():
            color = "green"
        else:
            color = "blue"
        if v_type != VertexType.BOUNDARY:
            nxg.add_node(v, 
                        label=str(v), 
                        color=color, 
                        title=f"Type: {v_type.name}")
            
    for e in g.edges():
        edge_type = g.edge_type(g.edge(*e))
        edge_color = "red" if edge_type == EdgeType.HADAMARD else "black"
        if g.type(e[0]) != VertexType.BOUNDARY and g.type(e[1]) != VertexType.BOUNDARY:
            nxg.add_edge(e[0], e[1])
            nxg[e[0]][e[1]]['color'] = edge_color

    # # Create PyVis network
    net = Network(notebook=False, directed=False)
    net.from_nx(nxg)
    net.toggle_physics(True)
    return net

    # net.show_buttons(filter_=['physics'])

    # html_path = "pyzx_graph.html"
    # net.save_graph(html_path)  # ✅ does not require render()


q_7_code = ["IIIXXXX", "IXXIIXX", "XIXIXIX", "IIIZZZZ", "IZZIIZZ", "ZIZIZIZ"]

tableau_to_graph(q_7_code)

st.title("CIAO")

