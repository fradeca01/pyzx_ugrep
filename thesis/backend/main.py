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


TIMEOUT_SECONDS = 15  


class SolveInput(BaseModel):
    inputs: List[int]
    adjacency_list: List[List[int]]

class StabilizerInput(BaseModel):
    selectedExample: Optional[str] = None
    n: int 
    k: int 
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
    estimated_time: Optional[float] = None

class ErrorResponse(BaseModel):
    success: bool
    error: str

class GraphData(BaseModel):
    inputs : List[int]
    stabilizers : List[str]
    adjacencyList : List[List[int]]
    qasmEncoder : str
    distance_upper_bound : int

class GraphInput(BaseModel):
    inputs : List[int]
    adjacencyList : List[List[int]]

class Job(BaseModel):
    process : Process
    status : str
    result : GraphData | None
    queue : Any
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
            if now - job.last_heartbeat > TIMEOUT_SECONDS:
                print(f"Job {job_id} scaduto (timeout). Pulizia in corso...")
                
                process = job.process
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
        print("HERRE")
        enc = tableau_to_graph_encoder(stabilizers)
        z = graph_to_universal_representation(enc)
        u = to_universal_graph_representation(z)
        distance_up_bound = distance_upper_bound(u)
        encoder_circuit = implement_encoder(u)
        qasmEncoder = encoder_circuit.to_qasm()
        
        d = {}

        d["inputs"] = u.inputs
        d["adjacency_list"] = u.adj
        d["stabilizers"] = stabilizers
        d["qasmEncoder"] = qasmEncoder
        d["distance_upper_bound"] = distance_up_bound

        rq.put({"success": True, "status" : "completed", "data": d})
    except Exception as e:
        print(e)
        rq.put({"success": False, "status": "failed", "error": str(e)})


def run_from_graph(inputs, adjacency_list, pivots, rq):
    try:

        ugr = UGR(inputs, adjacency_list, pivots, local_cliffords = {})

        stabilizers = to_stabilizer_tableau(ugr)
        dist  = distance_upper_bound(ugr)
        encoder = implement_encoder(ugr)

        d = {}

        d["stabilizers"] = stabilizers
        d["inputs"] = ugr.inputs
        d["adjacency_list"] = ugr.adj
        d["distance_upper_bound"] = dist
        d["qasmEncoder"] = encoder.to_qasm()

        print(d)

        rq.put({"success": True, "status" : "completed", "data": d})

    except Exception as e:
        print(e)
        rq.put({"success": False, "status": "failed", "error": str(e)})

@app.post("/from_dot", response_model=JobResponse | ErrorResponse)
async def from_dot(input_data : GraphInput):
    
    # print("AAAA")
    
    try:
        inputs = input_data.inputs
        adjacency_list = input_data.adjacencyList

        pivots = [-1 for _ in range(len(inputs))]

        for i in inputs:
            n_i = adjacency_list[i]
            for o in n_i:
                n_o = adjacency_list[o]
                ok = True
                for j in n_o:
                    if j != i and j in inputs:
                        ok = False
                if ok:
                    pivots[i] = o
                    break
        
        
        try:
            job_id = str(uuid.uuid4())
            queue = Queue() # For IPC
            process = Process(target=run_from_graph, args=(inputs, adjacency_list, pivots, queue))
            JOBS[job_id] = Job(
                process = process,
                status ="processing",
                result = None,
                last_heartbeat = time.time(),
                queue = queue
            )
            print("Process created:", process)
            print(JOBS)
            result = process.start()
            print(result)

            
            return {"success": True, "job_id": job_id}
        except Exception as e:
            print(e)
            return {"success": False, "error": str(e)}
    except Exception as e:
        return ErrorResponse(success=False, error=f"Error processing input: {str(e)}")



@app.post("/get_graph", response_model=JobResponse | ErrorResponse)
async def start_job(input_data: StabilizerInput):
    random = input_data.random
    selectedExample = input_data.selectedExample
    stabilizers = []
    n = 0
    k = 0

    try:
        if random:
            if input_data.n:
                n = int(input_data.n)
            else:
                raise HTTPException(status_code=400, detail="Parameter 'n' is required for random generation")
            
            if input_data.k:
                k = int(input_data.k)
            else:
                raise HTTPException(status_code=400, detail="Parameter 'k' is required for random generation")
            
            tableau = stim.Tableau.random(n)
            # print(tableau)
            for i in range(n - k):
                s = tableau.to_stabilizers()[i]
                stabilizers.append(str(s))
        elif selectedExample:
            example_data = examples_dict.get(selectedExample)
            if not example_data:
                raise HTTPException(status_code=400, detail="Selected example not found")
            n = example_data["n"]
            k = example_data["k"]
            stabilizers = example_data["stabilizers"]
        else:

            
            # print(input_data.stabilizers)

            if input_data.stabilizers != []:
                stabilizers = input_data.stabilizers
            else:
                raise HTTPException(status_code=400, detail="Stabilizers are required if no example is selected and random is false")
            
            if input_data.n:
                n = int(input_data.n)
            else:
                raise HTTPException(status_code=400, detail="Parameter 'n' is required for random generation")
            
            if input_data.k:
                k = int(input_data.k)
            else:
                raise HTTPException(status_code=400, detail="Parameter 'k' is required for random generation")
            
    except Exception as e:

        return ErrorResponse(success=False, error=f"Error processing input: {str(e)}")
        # return {"success": False, "error": f"Error processing input: {str(e)}"}

    # print("Stabilizers:", stabilizers)
    try:
        estimated_time = round(0.005 * (n ** 3), 1) 
        job_id = str(uuid.uuid4())
        queue = Queue() # For IPC
        process = Process(target=run_generate_graph, args=(stabilizers, n, k, queue))
        JOBS[job_id] = Job(
            process = process,
            status ="processing",
            result = None,
            last_heartbeat = time.time(),
            queue = queue
        )
        print("Process created:", process)
        print(JOBS)
        result = process.start()
        print(result)

        
        return {"success": True, "job_id": job_id, "estimated_time": estimated_time}
    except Exception as e:
        print(e)
        return {"success": False, "error": str(e)}




@app.get("/status/{job_id}", response_model=DataResponse)
async def check_status(job_id: str):

    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    job.last_heartbeat = time.time()
    queue = job.queue

    if not queue.empty():
        job_result = queue.get()
        job.status = job_result["status"]
        job.result = job_result.get("data", None) 

    print(job)

    if job.status == "completed" or job.status == "failed":
        return { "success" : True, "status" : job.status, "data" :  job.result } 

    process = job.process

    if process.is_alive():
        return {"success": True, "status": "processing"}
    else:
        job.status= "failed"
        return {"success": False, "status": "failed", "error": "Process died unexpectedly"}


@app.post("/cancel/{job_id}", response_model=DataResponse)
async def cancel_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return {"success": False, "status" : "failed" , "error": "Job not found"}

    process = job.process
    if process.is_alive():
        process.terminate()
        process.join()
    
    del JOBS[job_id]
    return {"success": True, "status": "cancelled"}

def run_minizinc_solver(inputs : List[int], adjacency_list : List[List[int]], result_queue : Queue):
    # try:
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
            result_queue.put({"success": True, "status" : "completed", "data": min_weight})
        else:
            result_queue.put({"success": False, "status" : "completed", "error": "Unsatisfiable"})

    # except Exception as e:
        # print("Error in MiniZinc solver:", str(e))
        # result_queue.put({"success": False, "status" : "failed",  "error": str(e)})

@app.post("/solve", response_model=JobResponse | ErrorResponse)
async def solve_minizinc(input_data: SolveInput):
    job_id = str(uuid.uuid4())
    
    n = len(input_data.adjacency_list)
    estimated_time = round(0.005 * (2 ** n), 1) 
    if estimated_time < 1: estimated_time = 1

    queue = Queue()
    process = Process(target=run_minizinc_solver, args=(input_data.inputs, input_data.adjacency_list, queue))
    print("Starting MiniZinc solver1...")
    process.start()

    JOBS[job_id] = Job(
        process = process,
        status = "processing",
        result = None,
        last_heartbeat = time.time(),
        queue =  queue,
    )

    return {
        "success": True, 
        "job_id": job_id, 
        "estimated_time": estimated_time
    }