import stim
from pyzx import *
import time
from tqdm import tqdm

n = 10
k = 5

num = 40


times = []

for n in tqdm(range(6,num), desc="test"):
    tableau = stim.Tableau.random(n)
    stabilizers = [str(s) for s in tableau.to_stabilizers()]
    ugr = stabilizers_to_UGR(stabilizers[0:n-k])
    model = to_distance_mzn(ugr.inputs, ugr.adj)

    start = time.perf_counter()
    a = compute_distance(ugr.inputs, ugr.adj) 
    end =time.perf_counter()

    times.append(end-start)

with open("mzn_times") as f:
    for t in times:
        f.write(f"{t}\n")


