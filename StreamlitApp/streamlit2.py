import stim
import os, sys
import networkx as nx
from pyvis.network import Network
import streamlit as st
import tempfile

# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pyzx import *


def tableau_to_graph(list, quiet = True):
    n = len(list[0])
    k = n - len(list)
    stabilizers = [stim.PauliString(x) for x in list]
    tableau = stim.Tableau.from_stabilizers(stabilizers, allow_underconstrained=True)
    stim_circ = tableau.to_circuit(method="elimination")
    qasm = stim_circ.to_qasm(open_qasm_version=3)
    pyzx_circ = Circuit.from_qasm(qasm)
    g = GraphState.from_circuit(pyzx_circ, k)
    g.to_canonical_form(quiet = quiet)
    return g

def hash_func(g : GraphState):
    """
    Hash function for GraphState objects.
    """
    return hash(tuple(g.get_states())) ^ hash(tuple(g.edges())) ^ hash(tuple(g.inputs())) ^ hash(tuple(g.outputs()))

@st.cache_data(hash_funcs={GraphState: hash_func}, show_spinner=True)
def pyzx_graph_to_pyvis(g : GraphState):

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



if 'example' not in st.session_state:
    st.session_state['example'] = "None"
if 'n_qubits' not in st.session_state:
    st.session_state['n_qubits'] = 7
if 'k_logical' not in st.session_state:
    st.session_state['k_logical'] = 1

def load_example():

    example = st.session_state.example
    if example == "Steane code":
        st.session_state['n_qubits'] = 7
        st.session_state['k_logical'] = 1
        example_stabilizers = ["IIIXXXX","IXXIIXX","XIXIXIX","IIIZZZZ","IZZIIZZ","ZIZIZIZ"]
    elif example == "Shor code":
        st.session_state['n_qubits'] = 9
        st.session_state['k_logical'] = 1
        example_stabilizers = ["ZZIIIIIII","ZIZIIIIII","IIIZZIIII","IIIZIZIII","IIIIIIZZI","IIIIIIZIZ","XXXXXXIII","IIIXXXXXX"]
    elif example == "Five qubit code":
        st.session_state['n_qubits'] = 5
        st.session_state['k_logical'] = 1
        example_stabilizers = ["XZZXI","IXZZX","XIXZZ","ZXIXZ"]
    else:
        example_stabilizers = []
    
    # Clear existing stabilizer inputs
    for i in range(20):  # Clear up to 20 possible stabilizers
        if f"stab_{i}" in st.session_state:
            st.session_state[f"stab_{i}"] = ""

    # Set the new stabilizers
    for i, s in enumerate(example_stabilizers):
        st.session_state[f"stab_{i}"] = s

    # st.rerun()


lc, rc = st.columns(2)


with st.sidebar:
    st.selectbox(
                "Load example:",
                ["None", "Steane code", "Shor code", "Five qubit code"],
                index=0, on_change=load_example(), key = "example")    
    
    c1, c2 = st.columns(2)
    with c1:
        n = st.number_input("Physical qubits (n)", min_value=1, max_value=128, step=1, key="n_qubits")
    with c2:
        k = st.number_input("Logical qubits (k)", min_value=0, max_value=n-1, step=1, key="k_logical")


    m = int(n) - int(k)
    stab_inputs = []
    with st.expander("Stabilizer Inputs", expanded=True):
        st.caption(f"Each stabilizer must have length {n} (alphabet: I X Y Z).")
        for i in range(m):
            # val = st.session_state.get(f"stab_{i}", "")
            st.text_input(f"S{i+1}", key=f"stab_{i}")
            stab_inputs.append(st.session_state.get(f"stab_{i}", "").strip().replace(" ", ""))

    run_btn = st.button("Convert")



if run_btn:
    tableau_list = [s for s in stab_inputs if s]
    valid = True
    if not tableau_list:
        st.error("Provide at least one stabilizer.")
        valid = False
    for s in tableau_list:
        if len(s) != n:
            st.error(f"'{s}' has length {len(s)} ≠ {n}.")
            valid = False
        if any(c not in "IXYZ" for c in s):
            st.error(f"Invalid symbol in '{s}'. Allowed: I X Y Z.")
            valid = False
    if m != len(tableau_list):
        st.warning(f"{len(tableau_list)} non-empty rows (expected {m}).")
    inferred_k = n - len(tableau_list)
    if inferred_k != k:
        st.info(f"Inferred k = n - m = {inferred_k} (entered k = {k}).")
    if valid:
        try:
            g = tableau_to_graph(tableau_list, quiet=True)
            net = pyzx_graph_to_pyvis(g)
            import tempfile, os
            with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
                net.save_graph(tmp.name)
                st.session_state.graph_html = open(tmp.name, "r").read()
                os.unlink(tmp.name)
        except Exception as e:
            st.error(f"Conversion failed: {e}")

@st.fragment()
def render_graph():
    st.write("# Graph View")
    if "graph_html" in st.session_state:
        st.components.v1.html(st.session_state.graph_html, height=600, width = 1000)
    else:
        st.info("Graph will appear here after conversion.")

render_graph()

