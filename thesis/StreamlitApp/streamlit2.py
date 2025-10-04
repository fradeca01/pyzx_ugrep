import stim
import os, sys
import networkx as nx
from pyvis.network import Network
import streamlit as st
import tempfile
from typing import Dict

# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pyzx import *

@st.dialog("Instructions")
def instructions_popup():
    st.markdown("""
    ### How to use this tool

    1. **Select an example code** (Steane, Shor, or Five-qubit) from the sidebar  
       or enter your own stabilizers manually.  
    2. Set the number of **physical qubits (n)** and **logical qubits (k)**.  
    3. Enter stabilizers in the input fields (alphabet: `I, X, Y, Z`).  
    4. Click **Convert** to generate a graph representation.  
    5. The graph will appear in the **Graph View** section below.  

    ⚠️ Make sure stabilizers are the correct length and contain only valid symbols.
    """)
    
def tableau_to_graph(list, quiet = True):
    n = len(list[0])
    k = n - len(list)
    stabilizers = [stim.PauliString(x) for x in list]
    tableau = stim.Tableau.from_stabilizers(stabilizers, allow_underconstrained=True)
    stim_circ = tableau.to_circuit(method="elimination")
    qasm = stim_circ.to_qasm(open_qasm_version=3)
    pyzx_circ = Circuit.from_qasm(qasm)
    g = pyzx_circ.to_graph()
    input_state = "0"*(n-k) + "/"*k
    g.apply_state(input_state)
    d = to_universal_graph_representation(g)
    # g = GraphState.from_circuit(pyzx_circ, k)
    # g.to_canonical_form(quiet = quiet)
    return d

def hash_func(g : GraphState):
    """
    Hash function for GraphState objects.
    """
    return hash(tuple(g.get_states())) ^ hash(tuple(g.edges())) ^ hash(tuple(g.inputs())) ^ hash(tuple(g.outputs()))

# @st.cache_data(hash_funcs={GraphState: hash_func}, show_spinner=True)
def pyzx_graph_to_pyvis(d : Dict):

    nxg = nx.Graph()
    bounds = []
    for v in d["vertices"]:
        v_type = v["t"]
        if v["id"] in d["inputs"]:
            color = "green"
        else:
            color = "blue"
        if v_type != VertexType.BOUNDARY:
            nxg.add_node(v["id"], 
                        color=color, 
                        title=f"Type: {v_type.name}")
        else:
            bounds.append(v["id"])
            
    for e in d["edges"]:
        vertexes = d["vertices"]
        edge_type = e[2]
        edge_color = "red" if edge_type == EdgeType.HADAMARD else "black"
        if e[0] not in bounds and e[1] not in bounds:
            nxg.add_edge(e[0], e[1])
            nxg[e[0]][e[1]]['color'] = edge_color

    # pos = nx.spring_layout(nxg, seed=42)  # nice spacing

    node_colors = [nxg.nodes[n]['color'] for n in nxg.nodes()]
    edge_colors = [nxg[u][v]['color'] for u,v in nxg.edges()]

    # Draw the graph
    # plt.figure(figsize=(10,8))
    # nx.draw_networkx_nodes(nxg, pos, node_color=node_colors, node_size=700)
    # nx.draw_networkx_edges(nxg, pos, edge_color=edge_colors, width=2)
    # nx.draw_networkx_labels(nxg, pos, font_size=10, font_color='black')

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

def clear_example():
    st.session_state["example"] = "None"




if "show_instructions" not in st.session_state:
    st.session_state.show_instructions = True

if st.session_state.show_instructions:
    instructions_popup()
    st.session_state.show_instructions = False

lc, rc = st.columns(2)


with st.sidebar:
    st.selectbox(
                "Load example:",
                ["None", "Steane code", "Shor code", "Five qubit code"],
                index=0, on_change=load_example, key = "example")    
    
    c1, c2 = st.columns(2)
    with c1:
        n = st.number_input("Physical qubits (n)", min_value=1, step=1, key="n_qubits")
    with c2:
        k = st.number_input("Logical qubits (k)", min_value=0, step=1, key="k_logical")


    m = int(n) - int(k)
    stab_inputs = []
    with st.expander("Stabilizer Inputs", expanded=True):
        st.caption(f"Each stabilizer must have length {n} (alphabet: I X Y Z).")
        for i in range(m):
            # val = st.session_state.get(f"stab_{i}", "")
            st.text_input(f"S{i+1}", key=f"stab_{i}", on_change=clear_example)
            stab_inputs.append(st.session_state.get(f"stab_{i}", "").strip().replace(" ", ""))

    run_btn = st.button("Convert")



if run_btn:
    tableau_list = [s for s in stab_inputs if s]
    valid = True
    if k >= n:
        st.error("k must be less than n.")
        valid = False
    elif not tableau_list:
        st.error("Provide at least one stabilizer.")
        valid = False
    else:
        for s in tableau_list:
            if len(s) != n:
                st.error(f"Stabilizer '{s}' has length {len(s)}, which is not {n}.")
                valid = False
            if any(c not in "IXYZ" for c in s):
                c = next(c for c in s if c not in "IXYZ")
                st.error(f"'{c}' is not a valid symbol. Allowed: I, X, Y, Z.")
                valid = False
    # if m != len(tableau_list):
    #     st.warning(f"{len(tableau_list)} non-empty rows (expected {m}).")
    # inferred_k = n - len(tableau_list)
    # if inferred_k != k:
    #     st.info(f"Inferred k = n - m = {inferred_k} (entered k = {k}).")
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
            st.session_state.graph_html = None
            st.error(f"Conversion failed: {e}")
    else:
        st.session_state.graph_html = None

        # st.info("Graph will appear here after conversion.")

@st.fragment()
def render_graph():
    if "graph_html" in st.session_state and st.session_state.graph_html is not None:
        st.write("# Graph View")
        graph_html = st.session_state.graph_html
        st.components.v1.html(graph_html, height=600, width = 1000)
    else:
        st.info("Graph will appear here after conversion.")

render_graph()

