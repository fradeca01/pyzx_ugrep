import asyncio
import time
import uuid
import json
import stim
from contextlib import asynccontextmanager
from multiprocessing import Process, Queue
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from minizinc import Instance, Model, Solver
import math

from pyzx import *


# Timeout for killing jobs
TIMEOUT_SECONDS = 15  


class SolveInput(BaseModel):
    inputs: List[int]
    adjacency_list: List[List[int]]

class StabilizerInput(BaseModel):
    selectedExample: Optional[str] = None
    n: Optional[int] = None
    k: Optional[int] = None
    random: bool = False
    stabilizers: Optional[List[str]] = []

class DataResponse(BaseModel):
    success: bool
    status: str
    data: Optional[Any] = None
    error: Optional[str] = None


class JobResponse(BaseModel):
    success: bool
    job_id: str

class GraphData(BaseModel):
    inputs : List[int]
    adjacency_list : List[List[int]]
    qasmEncoder : str
    distance_upper_bound : int

class Job(BaseModel):
    process : Process
    queue : Queue
    status : str
    result : GraphData
    last_heartbeat : float

    model_config = {
        "arbitrary_types_allowed": True
    }


# --- JOBS RUNNING ---
JOBS: Dict[str, Job] = {}


async def cleanup_stale_jobs():
    """Controlla periodicamente se ci sono job abbandonati."""
    print("Avvio task di pulizia job...")
    while True:
        await asyncio.sleep(5) 
        now = time.time()
        
        jobs_to_remove = []
        
        for job_id, job in JOBS.items():
            if now - job["last_heartbeat"] > TIMEOUT_SECONDS:
                print(f"Job {job_id} scaduto (timeout). Pulizia in corso...")
                
                process = job["process"]
                if process.is_alive():
                    process.terminate()
                    process.join()
                    print(f"Processo {process.pid} terminato forzatamente.")
                
                jobs_to_remove.append(job_id)
        
        # Rimuovi dal dizionario
        for job_id in jobs_to_remove:
            del JOBS[job_id]

@asynccontextmanager
async def lifespan(app: FastAPI):
    cleaner_task = asyncio.create_task(cleanup_stale_jobs())
    yield
    cleaner_task.cancel()

app = FastAPI(lifespan=lifespan)

origins = ["http://localhost:3000", "http://localhost"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    with open("example_dict.json", "r") as f:
        examples_dict = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    examples_dict = {}


def run_generate_graph(stabilizers, n, k, rq):
    try:
        d = from_tableau(stabilizers, n, k)
        distance_up_bound = distance_upper_bound(d)
        encoder_circuit = implement_encoder(d)
        qasmEncoder = encoder_circuit.to_qasm()
        d["qasmEncoder"] = qasmEncoder
        d["distance_upper_bound"] = distance_up_bound

        rq.put({"success": True, "status" : "completed", "data": d})
    except Exception as e:
        rq.put({"success": False, "status": "failed", "error": str(e)})


@app.post("/get_graph")
async def start_job(input_data: StabilizerInput) -> JobResponse:
    random = input_data.random
    selectedExample = input_data.selectedExample
    stabilizers = []
    n = 0
    k = 0

    if random:
        n = int(input_data.n)
        k = int(input_data.k)
        tableau = stim.Tableau.random(n)
        for i in range(n - k):
            s = tableau.to_stabilizers()[i]
            stabilizers.append(str(s))
    elif selectedExample:
        example_data = examples_dict.get(selectedExample)
        if not example_data:
            return {"success": False, "error": "Example not found"}
        n = example_data["n"]
        k = example_data["k"]
        stabilizers = example_data["stabilizers"]
    else:
        stabilizers = input_data.stabilizers
        n = int(input_data.n)
        k = int(input_data.k)

    
    try:
        job_id = str(uuid.uuid4())
        queue = Queue() # For IPC
        process = Process(target=run_generate_graph, args=(stabilizers, n, k, queue))
        JOBS[job_id] = {
            "process": process,
            "status": "processing",
            "result": None,
            "last_heartbeat": time.time(),
            "queue" : queue
        }
        print(JOBS)
        result = process.start()
        print(result)


        return {"success": True, "job_id": job_id}
    except Exception as e:
        return {"success": False, "error": str(e)}




@app.get("/status/{job_id}")
async def check_status(job_id: str) -> DataResponse:

    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    job["last_heartbeat"] = time.time()
    queue = job["queue"]

    if not queue.empty():
        job_result = queue.get()
        job["status"] = job_result["status"]
        job["result"] = job_result["data"]

    print(job)

    if job["status"] == "completed" or job["status"] == "failed":
        return { "success" : True, "status" : job["status"], "data" :  job["result"] } 

    process = job["process"]

    if process.is_alive():
        return {"success": True, "status": "processing"}
    else:
        job["status"] = "failed"
        return {"success": False, "status": "failed", "error": "Process died unexpectedly"}


@app.post("/cancel/{job_id}")
async def cancel_job(job_id: str) -> DataResponse:
    job = JOBS.get(job_id)
    if not job:
        return {"success": False, "status" : "failed" , "error": "Job not found"}

    process = job["process"]
    if process.is_alive():
        process.terminate()
        process.join()
    
    del JOBS[job_id]
    return {"success": True, "status": "cancelled"}

def run_minizinc_solver(inputs, adjacency_list, result_queue):
    try:
        # 1. Preparazione Dati per MiniZinc
        # Convertiamo liste Python in formati compatibili con MiniZinc (1-based index spesso richiesto)
        # Ma il tuo modello usa indici interi, assumiamo che 1..N sia meglio per MZN.

        print("Starting MiniZinc solver2...")
        
        num_nodes = len(adjacency_list)
        # Mappa 0-based index (Python) a 1-based index (MiniZinc)
        I_nodes = {i + 1 for i in inputs}
        all_nodes = set(range(1, num_nodes + 1))
        O_P_nodes = all_nodes - I_nodes
        
        # Matrice di adiacenza
        adj = [[False for _ in range(num_nodes)] for _ in range(num_nodes)]
        for i, neighbors in enumerate(adjacency_list):
            for neighbor in neighbors:
                # Adiacenza non diretta
                adj[i][neighbor] = True
                adj[neighbor][i] = True
                
        # Initial lights (tutti 0 per trovare la distanza minima del codice stesso)
        initial_lights = [0] * (num_nodes + 1) # Padding per 1-based indexing

        # 2. Caricamento Modello
        print("Starting MiniZinc solver3...")
        model = Model("qlo.mzn") 
        solver = Solver.lookup("gecode") # O "coin-bc", "chuffed"
        print("Starting MiniZinc solver4...")
        instance = Instance(solver, model)

        instance["I_nodes"] = I_nodes
        instance["O_P_nodes"] = O_P_nodes
        instance["adj"] = adj
        # instance["initial_lights"] è un array su O_P_nodes. 
        # Dobbiamo passarlo correttamente. MiniZinc si aspetta un array indicizzato.
        # Per semplicità, passiamo una lista della lunghezza corretta se l'enum è int.
        instance["initial_lights"] = [0] * len(O_P_nodes) 

        print("Starting MiniZinc solver...")
        # 3. Risoluzione
        result = instance.solve()

        if result:
            min_weight = result["objective"]
            result_queue.put({"success": True, "data": min_weight})
        else:
            result_queue.put({"success": False, "error": "Unsatisfiable"})

    except Exception as e:
        print("Error in MiniZinc solver:", str(e))
        result_queue.put({"success": False, "status" : "failed",  "error": str(e)})

@app.post("/solve")
async def solve_minizinc(input_data: SolveInput) -> JobResponse:
    job_id = str(uuid.uuid4())
    
    # --- STIMA DEL TEMPO ---
    # Una semplice euristica: N^2 o esponenziale a seconda della complessità
    n = len(input_data.adjacency_list)
    estimated_time = round(0.005 * (n ** 2), 1) # Esempio: 100 nodi -> 50 secondi
    if estimated_time < 1: estimated_time = 1

    queue = Queue()
    process = Process(target=run_minizinc_solver, args=(input_data.inputs, input_data.adjacency_list, queue))
    print("Starting MiniZinc solver1...")
    process.start()

    JOBS[job_id] = {
        "process": process,
        "status": "processing",
        "result": None,
        "last_heartbeat": time.time(),
        "queue": queue,
    }

    return {
        "success": True, 
        "job_id": job_id, 
        # "estimated_time": estimated_time
    }