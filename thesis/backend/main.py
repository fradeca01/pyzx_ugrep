# main.py
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import networkx as nx
import stim
from pyvis.network import Network
import json
from fastapi.middleware.cors import CORSMiddleware
# --- IMPORTA IL TUO PACCHETTO ---
# Sostituisci "mio_pacchetto_personale" con il nome
# con cui importeresti normalmente il tuo pacchetto
from pyzx import * 

# --- Modelli di Dati ---
# Questo definisce i dati che ci aspettiamo dal frontend.
# FastAPI li controllerà automaticamente.
class StabilizerInput(BaseModel):
    selectedExample: Optional[str] = None
    n: int = None
    k: int = None
    random: bool = False
    stabilizers: List[str] = []

# --- Crea l'applicazione API ---
app = FastAPI()

# --- Endpoint di Test ---
# Un semplice URL per vedere se il server è vivo
@app.get("/")
def read_root():
    return {"message": "Ciao! Il backend è attivo."}

origins = [
    "http://localhost:3000", # L'indirizzo del tuo frontend React
    "http://localhost",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Permetti tutti i metodi (GET, POST, ecc.)
    allow_headers=["*"], # Permetti tutti gli header
)

try:
    with open("example_dict.json", "r") as f:
        # Store the loaded data in a global variable
        examples_dict = json.load(f)
except FileNotFoundError:
    examples_dict = {"error": "File not found. Please create 'my_data.json'."}
except json.JSONDecodeError:
    examples_dict = {"error": "Failed to decode JSON from 'my_data.json'."}
# -----------------------------------------------


# --- ENDPOINT DI CALCOLO ---
# Questo è l'URL che il tuo frontend chiamerà!
# # È un POST perché inviamo dati (n, k, ecc.)
# @app.post("/calculate")
# async def run_calculation(input_data: StabilizerInput):
#     # input_data ora contiene i dati inviati da React
#     # (es. input_data.n, input_data.stabilizers)
    
#     try:
#         # --- QUI CHIAMI IL TUO PACCHETTO ---
#         # Esegui la logica complessa del tuo pacchetto Python
#         # passando i dati ricevuti dal frontend.
#         result = mio_pacchetto_personale.mia_funzione_principale(
#             n=input_data.n,
#             k=input_data.k,
#             example=input_data.selectedExample,
#             stabilizers=input_data.stabilizers
#         )
        
#         # Invia il risultato al frontend
#         return {"success": True, "data": result}
        
#     except Exception as e:
#         # In caso di errore nel tuo pacchetto, invia un messaggio chiaro
#         return {"success": False, "error": str(e)}
    
# async def pyzx_graph_to_pyvis(d):

#     nxg = nx.Graph()
#     bounds = []
#     for v in range(len(d["adjacency_list"])):
#         # v_type = v["t"]
#         if v in d["inputs"]:
#             color = "green"
#         else:
#             color = "blue"
#         # if v_type != VertexType.BOUNDARY:
#         nxg.add_node(v, 
#                     color=color, 
#                     )
#         # else:
#         # bounds.append(v["id"])

#     adj = d["adjacency_list"]

#     for i in range(len(adj)):
#         for j in adj[i]:
#             if i < j:
#                 nxg.add_edge(i, j)
#                 nxg[i][j]['color'] = "black"
            
#     # for e in d["edges"]:
#     #     vertexes = d["vertices"]
#     #     edge_type = e[2]
#     #     edge_color = "red" if edge_type == EdgeType.HADAMARD else "black"
#     #     if e[0] not in bounds and e[1] not in bounds:
#     #         nxg.add_edge(e[0], e[1])
#     #         nxg[e[0]][e[1]]['color'] = edge_color

#     pos = nx.spring_layout(nxg, seed=42)  # nice spacing

#     node_colors = [nxg.nodes[n]['color'] for n in nxg.nodes()]
#     edge_colors = [nxg[u][v]['color'] for u,v in nxg.edges()]

#     # Draw the graph
#     # plt.figure(figsize=(10,8))
#     nx.draw_networkx_nodes(nxg, pos, node_color=node_colors, node_size=700)
#     nx.draw_networkx_edges(nxg, pos, edge_color=edge_colors, width=2)
#     # nx.draw_networkx_labels(nxg, pos, font_size=10, font_color='white')

#     # Add title to the plot
#     # plt.title("5 qubit code", fontsize=16, pad=20)

#     # plt.axis('off')
#     # plt.show()

#     net = Network(notebook=True, directed=False)
#     net.from_nx(nxg)
#     return net

@app.post("/run")
async def tableau_to_graph(input_data: StabilizerInput):

    random = input_data.random
    selectedExample = input_data.selectedExample

    stabilizers = []

    try:
        print(selectedExample)

        if random:
            n = int(input_data.n)
            k = int(input_data.k)
            stabilizers = []
            tableau = stim.Tableau.random(n)
            for i in range(n - k):
                s = tableau.to_stabilizers()[i]
                stabilizers.append(str(s))
        elif selectedExample:
            example_data = examples_dict.get(selectedExample)
            # print(example_data)
            n = example_data["n"]
            k = example_data["k"]
            stabilizers = example_data["stabilizers"]
            # print(stabilizers)
        else:
            stabilizers = input_data.stabilizers
            n = int(input_data.n)
            k = int(input_data.k)

    # print("Stabilizers:", stabilizers)
    # print("n:", n)
    # print("k:", k)

        d = from_tableau(stabilizers, n, k)
        print(d)
        up_bound =  distance_upper_bound(d)
        circuit = implement_encoder(d)
        qasmEconder = circuit.to_qasm()
        d["qasmEncoder"] = qasmEconder
        d["distance_lower_bound"] = up_bound
        print(d)
        return {"success" : True, "data" : d}
    except Exception as e:
        print("error", e)
        return {"success" : False, "data" : str(e)}
