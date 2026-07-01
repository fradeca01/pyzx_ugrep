import asyncio
import time
import uuid
import json
import os
import stim
from contextlib import asynccontextmanager
from multiprocessing import Process, Queue
from queue import Empty
from typing import Dict, Any, Optional, List
import psutil
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from ugr import *

TIMEOUT_SECONDS = int(os.getenv("UGR_JOB_IDLE_TIMEOUT_SECONDS", "15"))
MAX_JOB_RUNTIME_SECONDS = int(os.getenv("UGR_MAX_JOB_RUNTIME_SECONDS", "60"))
MAX_ACTIVE_JOBS = int(os.getenv("UGR_MAX_ACTIVE_JOBS", "2"))
MAX_GENERATE_N = int(os.getenv("UGR_MAX_GENERATE_N", "40"))
MAX_DOT_NODES = int(os.getenv("UGR_MAX_DOT_NODES", "40"))
MAX_SOLVE_NODES = int(os.getenv("UGR_MAX_SOLVE_NODES", "24"))
MAX_STABILIZERS = int(os.getenv("UGR_MAX_STABILIZERS", "64"))


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
    stabilizers: List[str] = Field(default_factory=list)

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
    started_at : float
    model_config = {
        "arbitrary_types_allowed": True
    }

JOBS: Dict[str, Job] = {}


def active_job_count() -> int:
    return sum(1 for job in JOBS.values() if job.process.is_alive())


def capacity_error() -> Optional[str]:
    running_jobs = active_job_count()
    if running_jobs >= MAX_ACTIVE_JOBS:
        return (
            f"Server is busy: {running_jobs} active jobs are already running. "
            f"The limit is {MAX_ACTIVE_JOBS}."
        )
    return None


def validate_code_parameters(n: int, k: int) -> Optional[str]:
    if n <= 0:
        return "Parameter 'n' must be positive"
    if k < 0:
        return "Parameter 'k' must be non-negative"
    if k >= n:
        return "Parameters must satisfy n > k"
    if n > MAX_GENERATE_N:
        return f"Parameter 'n' is too large. Maximum allowed value is {MAX_GENERATE_N}."
    return None


def validate_stabilizer_input(stabilizers: List[str], n: int, k: int) -> Optional[str]:
    if len(stabilizers) != n - k:
        return f"Expected {n - k} stabilizers, got {len(stabilizers)}."
    if len(stabilizers) > MAX_STABILIZERS:
        return f"Too many stabilizers. Maximum allowed value is {MAX_STABILIZERS}."
    return None


def validate_adjacency_list(inputs: List[int], adjacency_list: List[List[int]], max_nodes: int) -> Optional[str]:
    node_count = len(adjacency_list)
    if node_count <= 0:
        return "Graph must contain at least one node"
    if node_count > max_nodes:
        return f"Graph is too large. Maximum allowed node count is {max_nodes}."

    input_set = set(inputs)
    if len(input_set) != len(inputs):
        return "Input nodes must be distinct"
    if any(input_vertex < 0 or input_vertex >= node_count for input_vertex in input_set):
        return "Input nodes must be valid graph vertices"

    for vertex, neighbors in enumerate(adjacency_list):
        if len(neighbors) != len(set(neighbors)):
            return f"Duplicate neighbors in adjacency list for vertex {vertex}"
        for neighbor in neighbors:
            if neighbor < 0 or neighbor >= node_count:
                return f"Invalid neighbor {neighbor} in adjacency list for vertex {vertex}"
            if vertex not in adjacency_list[neighbor]:
                return f"Adjacency list is not symmetric for edge ({vertex}, {neighbor})"
    return None


def close_job_resources(job: Job) -> None:
    try:
        job.queue.close()
        job.queue.cancel_join_thread()
    except Exception:
        pass


def stop_job(job: Job) -> None:
    process = job.process
    if process.is_alive() and process.pid:
        kill_process_tree(process.pid)
    process.join(timeout=3)
    close_job_resources(job)


def start_limited_job(target, *args) -> tuple[Optional[str], Optional[str]]:
    error = capacity_error()
    if error:
        return None, error

    now = time.time()
    job_id = str(uuid.uuid4())
    queue = Queue()
    process = Process(target=target, args=(*args, queue))
    JOBS[job_id] = Job(
        process=process,
        status="processing",
        last_heartbeat=now,
        started_at=now,
        queue=queue,
    )

    try:
        process.start()
    except Exception as exc:
        job = JOBS.pop(job_id)
        close_job_resources(job)
        return None, f"Error spawning the process: {str(exc)}"

    return job_id, None

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
            idle_timeout = now - job.last_heartbeat > TIMEOUT_SECONDS
            runtime_timeout = now - job.started_at > MAX_JOB_RUNTIME_SECONDS

            if idle_timeout or runtime_timeout:
                reason = "runtime limit" if runtime_timeout else "idle timeout"
                print(f"Job {job_id} expired ({reason}). Cleaning up...")
                stop_job(job)
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

        if len(old_inputs) != len(set(old_inputs)):
            return {"success": False, "error": "Input nodes must be distinct"}
        if len(old_adjacency_list) > MAX_DOT_NODES:
            return {
                "success": False,
                "error": f"Graph is too large. Maximum allowed node count is {MAX_DOT_NODES}.",
            }

        print("OLD INPUTS:", old_inputs)
        print("OLD ADJACENCY LIST:", old_adjacency_list)

        input_set = set(old_inputs)
        all_nodes_set = set(old_adjacency_list.keys())
        others_set = all_nodes_set - input_set

        new_order = old_inputs + sorted(others_set)

        old_to_new_map = {node : i for i, node in enumerate(new_order)}

        inputs = [old_to_new_map[i] for i in old_inputs]

        adjacency_list = [[] for _ in range(len(new_order))]

        for old_node, old_neigh in old_adjacency_list.items():
            new_node = old_to_new_map[old_node]
            for neigh in old_neigh:
                if neigh not in old_to_new_map:
                    return {"success": False, "error": f"Unknown neighbor {neigh} in DOT graph"}
                new_neigh = old_to_new_map[neigh]
                adjacency_list[new_node].append(new_neigh)

        validation_error = validate_adjacency_list(inputs, adjacency_list, MAX_DOT_NODES)
        if validation_error:
            return {"success": False, "error": validation_error}

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

        if any(pivot == -1 for pivot in pivots):
            return {"success": False, "error": "Could not find a valid pivot for every input"}
        
        try:
            job_id, error = start_limited_job(run_from_graph, inputs, adjacency_list, pivots)
            if error:
                return {"success": False, "error": error}
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
    stabilizers: List[str] = []
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

            validation_error = validate_code_parameters(n, k)
            if validation_error:
                return {"success": False, "error": validation_error}
            
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

            validation_error = validate_code_parameters(n, k)
            if validation_error:
                return {"success": False, "error": validation_error}
            validation_error = validate_stabilizer_input(stabilizers, n, k)
            if validation_error:
                return {"success": False, "error": validation_error}
        else:
            if input_data.stabilizers:
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

            validation_error = validate_code_parameters(n, k)
            if validation_error:
                return {"success": False, "error": validation_error}
            validation_error = validate_stabilizer_input(stabilizers, n, k)
            if validation_error:
                return {"success": False, "error": validation_error}
            
    except Exception as e:
        return {"success" : False, "error" : f"Error processing input: {str(e)}"}
    try:
        estimated_time = round(0.005 * (n ** 3), 1) 
        job_id, error = start_limited_job(run_generate_graph, stabilizers, n, k)
        if error:
            return {"success": False, "error": error}

        
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
        if job.last_heartbeat - job.started_at > MAX_JOB_RUNTIME_SECONDS:
            stop_job(job)
            del JOBS[job_id]
            return {
                "success": False,
                "error": f"Job exceeded the maximum runtime of {MAX_JOB_RUNTIME_SECONDS} seconds",
            }

        queue = job.queue

        try:
            job_result = queue.get_nowait()
        except Empty:
            job_result = None

        if job_result is not None:
            print("RESULT IN QUEUE")
            print("JOB RESULT:", job_result)
            succ = job_result.get("success")
            result = job_result.get("data", None) 
            error = job_result.get("error", None)
            job.process.join(timeout=3)
            close_job_resources(job)
            del JOBS[job_id]

            if succ == True: 
                return { "success" : True, "status" : "completed", "data" :  result } 
            elif succ==False:
                return { "success" : False, "error" : error } 

        process = job.process

        if process.is_alive():
            return {"success": True, "status": "processing", "data" : None}
        else:
            process.join(timeout=3)
            close_job_resources(job)
            del JOBS[job_id]
            return {"success": False, "error": "Process is dead and cannot retrieve status"}
    except Exception as e:
        print(e)
        return {"success": False, "error": f"Error retrieving status: {str(e)}"}


@app.post("/cancel/{job_id}", response_model=DataResponse)
async def cancel_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return {"success": False, "status" : "failed" , "error": "Job not found"}

    stop_job(job)
    
    del JOBS[job_id]
    return {"success": True, "status": "cancelled"}

def run_minizinc_solver(inputs : List[int], adjacency_list : List[List[int]], result_queue : Queue):   
        try:
            result = compute_distance(inputs, adjacency_list)
            if result != -1:
                min_weight = result
                result_queue.put({"success": True, "status" : "completed", "data": min_weight})
            else:
                result_queue.put({"success": False, "status" : "completed", "error": "Unsatisfiable"})
        except Exception as e:
            # print("EXPE")
            result_queue.put({"success" : False, "error" : "Unable to start the solver"})
            

@app.post("/solve", response_model=JobResponse | ErrorResponse)
async def solve_minizinc(input_data: SolveInput):
    validation_error = validate_adjacency_list(
        input_data.inputs,
        input_data.adjacency_list,
        MAX_SOLVE_NODES,
    )
    if validation_error:
        return {"success": False, "error": validation_error}
    
    n = len(input_data.adjacency_list)
    estimated_time = round(0.005 * (2 ** n), 1) 
    if estimated_time < 1: estimated_time = 1

    print("Starting MiniZinc solver1...")
    job_id, error = start_limited_job(
        run_minizinc_solver,
        input_data.inputs,
        input_data.adjacency_list,
    )
    if error:
        return {"success": False, "error": error}

    return {
        "success": True, 
        "job_id": job_id, 
        "estimated_time": estimated_time
    }
