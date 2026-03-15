import asyncio
import time
import uuid
import json
import stim
from contextlib import asynccontextmanager
from multiprocessing import Process, Queue
from typing import Dict, Any, Optional, List
import psutil
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from minizinc import Instance, Model, Solver
import math

from pyzx import *


TIMEOUT_SECONDS = 15  


# success: True request completed correctly -> Workflow is running appropiately
# status: Failed -> Returning an error

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
    adjacencyList : List[tuple[int, List[int]]]

class JobResult(BaseModel):
    status : str
    error : str | None
    data : GraphData | None

class Job(BaseModel):
    process : Process
    status : str
    queue : Any
    last_heartbeat : float
    model_config = {
        "arbitrary_types_allowed": True
    }

JOBS: Dict[str, Job] = {}

def kill_process_tree(pid: int):
    """
    Kills a process and all its children (e.g. the Gecode solver).
    """
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        
        for child in children:
            print(f"Killing child process: {child.pid}")
            child.terminate()
        
        _, alive = psutil.wait_procs(children, timeout=3)
        for p in alive:
            p.kill() 

        print(f"Killing parent process: {parent.pid}")
        parent.terminate()
        parent.wait(timeout=3)
        
    except psutil.NoSuchProcess:
        print("Process already dead.")
    except Exception as e:
        print(f"Error killing process tree: {e}")

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
                    if process.pid:
                        kill_process_tree(process.pid)
                    process.join()
                    print(f"Processo {process.pid} terminato forzatamente.")
                
                jobs_to_remove.append(job_id)
        
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
    with open("./example_dict.json", "r") as f:
        examples_dict = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    examples_dict = {}


def run_generate_graph(stabilizers, n, k, rq):
    try:
        enc = stabilizers_to_ZX_graph(stabilizers)
        z = graph_to_ZXCF(enc)
        u = ZXCF_to_UGR(z)
        distance_up_bound = distance_upper_bound(u)
        encoder_circuit = implement_encoder(u)
        qasmEncoder = encoder_circuit.to_qasm()
        
        d = {}

        d["inputs"] = u.inputs
        d["adjacency_list"] = u.adj
        d["stabilizers"] = stabilizers
        d["qasmEncoder"] = qasmEncoder
        d["distance_upper_bound"] = distance_up_bound

        rq.put({"success" : True, "status" : "completed", "error" : None, "data": d})
    except Exception as e:
        print(e)
        rq.put({"success" : False  , "status": "completed", "error": f"Cannot generate graph: {str(e)}", "data" : None})


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

        rq.put({"success" : True, "status" : "completed", "error" : None, "data": d})

    except Exception as e:
        rq.put({"success" : False, "status": "completed", "error": f"Cannot generate graph: {str(e)}", "data" : None})


@app.post("/from_dot", response_model=JobResponse | ErrorResponse)
async def from_dot(input_data : GraphInput):
      
    try:
        old_inputs = input_data.inputs
        old_adjacency_list = {item[0]: set(item[1]) for item in input_data.adjacencyList}

        print("OLD INPUTS:", old_inputs)
        print("OLD ADJACENCY LIST:", old_adjacency_list)

        input_set = set(old_inputs)
        all_nodes_set = set(old_adjacency_list.keys())
        others_set = all_nodes_set - input_set

        new_order = list(input_set) + list(others_set)

        old_to_new_map = {node : i for i, node in enumerate(new_order)}

        inputs = [old_to_new_map[i] for i in old_inputs]

        adjacency_list = [[] for _ in range(len(old_adjacency_list))]

        for old_node, old_neigh in old_adjacency_list.items():
            new_node = old_to_new_map[old_node]
            for neigh in old_neigh:
                new_neigh = old_to_new_map[neigh]
                adjacency_list[new_node].append(new_neigh)

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
            queue = Queue() 
            process = Process(target=run_from_graph, args=(inputs, adjacency_list, pivots, queue))
            JOBS[job_id] = Job(
                process = process,
                status ="processing",
                last_heartbeat = time.time(),
                queue = queue
            )
            # print("Process created:", process)
            print(JOBS)
            result = process.start()
            # print(result)

            # print("Process started:", process)

            
            return {"success": True, "job_id": job_id}
        except Exception as e:
            return {"success": False, "error": f"Error spawning the process: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Error processing the input: {str(e)}"}



@app.post("/get_graph", response_model=JobResponse | ErrorResponse)
async def start_job(input_data: StabilizerInput):
    random = input_data.random
    selectedExample = input_data.selectedExample
    print(selectedExample)
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
        return {"success" : False, "error" : f"Error processing input: {str(e)}"}
    try:
        estimated_time = round(0.005 * (n ** 3), 1) 
        job_id = str(uuid.uuid4())
        queue = Queue() 
        process = Process(target=run_generate_graph, args=(stabilizers, n, k, queue))
        JOBS[job_id] = Job(
            process = process,
            status ="processing",
            last_heartbeat = time.time(),
            queue = queue
        )
        result = process.start()

        
        return {"success": True, "job_id": job_id, "estimated_time": estimated_time}
    except Exception as e:
        print(str(e))
        return {"success": False, "error": str(e)}


@app.get("/status/{job_id}", response_model=DataResponse | ErrorResponse)
async def check_status(job_id: str):
    print("CALLED")
    try: 
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found or expired")

        job.last_heartbeat = time.time()
        queue = job.queue

        if not queue.empty():
            print("RESULT IN QUEUE")
            job_result = queue.get()
            print("JOB RESULT:", job_result)
            succ = job_result.get("success")
            result = job_result.get("data", None) 
            error = job_result.get("error", None)

            if succ == True: 
                return { "success" : True, "status" : "completed", "data" :  result } 
            elif succ==False:
                return { "success" : False, "error" : error } 

        process = job.process

        if process.is_alive():
            return {"success": True, "status": "processing", "data" : None}
        else:
            return {"success": False, "error": "Process is dead and cannot retieve status"}
    except Exception as e:
        print(e)
        return {"success": False, "error": f"Error retrieving status: {str(e)}"}


@app.post("/cancel/{job_id}", response_model=DataResponse)
async def cancel_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return {"success": False, "status" : "failed" , "error": "Job not found"}

    process = job.process
    if process.is_alive():
        if process.pid:
            kill_process_tree(process.pid)
        process.join()
    
    del JOBS[job_id]
    return {"success": True, "status": "cancelled"}

def run_minizinc_solver(inputs : List[int], adjacency_list : List[List[int]], result_queue : Queue):   
        num_nodes = len(adjacency_list)
        I_nodes = {i + 1 for i in inputs}
        all_nodes = set(range(1, num_nodes + 1))
        O_P_nodes = all_nodes - I_nodes
        
        adj = [[False for _ in range(num_nodes)] for _ in range(num_nodes)]
        for i, neighbors in enumerate(adjacency_list):
            for neighbor in neighbors:
                adj[i][neighbor] = True
                adj[neighbor][i] = True
                
        initial_lights = [0] * (num_nodes + 1) 

        try:
            model = Model("qlo.mzn") 
            solver = Solver.lookup("gecode")
            instance = Instance(solver, model)

            instance["I_nodes"] = I_nodes
            instance["O_P_nodes"] = O_P_nodes
            instance["adj"] = adj
            instance["initial_lights"] = [0] * len(O_P_nodes) 


            print("Starting MiniZinc solver...")
            result = instance.solve()

            if result:
                min_weight = result["objective"]
                result_queue.put({"success": True, "status" : "completed", "data": min_weight})
            else:
                result_queue.put({"success": False, "status" : "completed", "error": "Unsatisfiable"})
        except Exception as e:
            print("EXPE")
            result_queue.put({"success" : False, "error" : "Unable to start the solver"})
  

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
        last_heartbeat = time.time(),
        queue =  queue,
    )

    return {
        "success": True, 
        "job_id": job_id, 
        "estimated_time": estimated_time
    }