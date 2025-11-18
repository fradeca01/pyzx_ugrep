import asyncio
import time
import uuid
import json
from contextlib import asynccontextmanager
from multiprocessing import Process, Queue
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# --- IMPORTA IL TUO PACCHETTO ---
from pyzx import * # --- CONFIGURAZIONE ---
TIMEOUT_SECONDS = 15  # Se il frontend non si fa sentire per 15s, uccidiamo il job

# --- Modelli di Dati ---
class StabilizerInput(BaseModel):
    selectedExample: Optional[str] = None
    n: int = None
    k: int = None
    random: bool = False
    stabilizers: List[str] = []

# --- GLOBAL STATE ---
JOBS: Dict[str, Any] = {}

# --- TASK DI PULIZIA (IL "BIDELLO") ---
async def cleanup_stale_jobs():
    """Controlla periodicamente se ci sono job abbandonati."""
    print("Avvio task di pulizia job...")
    while True:
        await asyncio.sleep(5) # Controlla ogni 5 secondi
        now = time.time()
        
        # Creiamo una lista delle chiavi da rimuovere per non modificare il dizionario mentre lo iteriamo
        jobs_to_remove = []
        
        for job_id, job in JOBS.items():
            # Se sono passati troppi secondi dall'ultimo "colpo" (polling)
            if now - job["last_heartbeat"] > TIMEOUT_SECONDS:
                print(f"Job {job_id} scaduto (timeout). Pulizia in corso...")
                
                # Se il processo sta ancora girando, lo uccidiamo
                process = job["process"]
                if process.is_alive():
                    process.terminate()
                    process.join()
                    print(f"Processo {process.pid} terminato forzatamente.")
                
                jobs_to_remove.append(job_id)
        
        # Rimuovi dal dizionario
        for job_id in jobs_to_remove:
            del JOBS[job_id]

# --- LIFESPAN (Gestione Avvio/Arresto Server) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # All'avvio del server, lanciamo il task di pulizia
    cleaner_task = asyncio.create_task(cleanup_stale_jobs())
    yield
    # Alla chiusura del server, cancelliamo il task
    cleaner_task.cancel()

app = FastAPI(lifespan=lifespan)

# --- Configurazione CORS ---
origins = ["http://localhost:3000", "http://localhost"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Caricamento Dati ---
try:
    with open("example_dict.json", "r") as f:
        examples_dict = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    examples_dict = {}


# --- FUNZIONE WORKER ---
def run_computation_task(stabilizers, n, k, result_queue):
    try:
        d = from_tableau(stabilizers, n, k)
        up_bound = distance_upper_bound(d)
        circuit = implement_encoder(d)
        qasmEncoder = circuit.to_qasm()
        d["qasmEncoder"] = qasmEncoder
        d["distance_lower_bound"] = up_bound
        result_queue.put({"success": True, "data": d})
    except Exception as e:
        result_queue.put({"success": False, "error": str(e)})


# --- ENDPOINT 1: START ---
@app.post("/run")
async def start_job(input_data: StabilizerInput):
    # ... (logica di preparazione dati uguale a prima) ...
    random = input_data.random
    selectedExample = input_data.selectedExample
    stabilizers = []
    n = 0
    k = 0

    try:
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
    except Exception as e:
        return {"success": False, "error": str(e)}

    job_id = str(uuid.uuid4())
    queue = Queue()
    process = Process(target=run_computation_task, args=(stabilizers, n, k, queue))
    process.start()

    # SALVIAMO IL TIMESTAMP DI ADESSO
    JOBS[job_id] = {
        "process": process,
        "queue": queue,
        "status": "processing",
        "result": None,
        "last_heartbeat": time.time()  # <--- IMPORTANTE: Inizia il conto alla rovescia
    }

    return {"success": True, "job_id": job_id}


# --- ENDPOINT 2: STATUS (Con Heartbeat) ---
@app.get("/status/{job_id}")
async def check_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        # Se il job non esiste più (magari cancellato dal timeout), diamo 404
        raise HTTPException(status_code=404, detail="Job not found or expired")

    # AGGIORNIAMO IL BATTITO CARDIACO
    # Ogni volta che il frontend chiama questo endpoint, resettiamo il timer
    job["last_heartbeat"] = time.time()

    if job["status"] == "completed":
        return job["result"]

    process = job["process"]
    queue = job["queue"]

    if process.is_alive():
        return {"success": True, "status": "processing"}
    
    if not queue.empty():
        result = queue.get()
        job["status"] = "completed"
        job["result"] = result
        process.join()
        return result
    else:
        job["status"] = "failed"
        return {"success": False, "status": "failed", "error": "Process died unexpectedly"}


# --- ENDPOINT 3: CANCEL ---
@app.post("/cancel/{job_id}")
async def cancel_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return {"success": False, "error": "Job not found"}

    process = job["process"]
    if process.is_alive():
        process.terminate()
        process.join()
    
    del JOBS[job_id]
    return {"success": True, "status": "cancelled"}