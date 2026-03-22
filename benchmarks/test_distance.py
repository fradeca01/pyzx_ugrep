import stim
from ugr import *
import time
from tqdm import tqdm

k = 4

num = 35

iterations = 5

times = []
with open("mzn_times2", 'w') as f:

    for n in tqdm(range(5,num), desc=f"test"):
        sum = 0
        for i in range(iterations):
            tableau = stim.Tableau.random(n)
            stabilizers = [str(s) for s in tableau.to_stabilizers()]
            ugr = stabilizers_to_UGR(stabilizers[0:n-k])
            model = to_distance_mzn(ugr.inputs, ugr.adj)

            start = time.perf_counter()
            a = compute_distance(ugr.inputs, ugr.adj) 
            end =time.perf_counter()

            sum += (end-start)
        t = sum / iterations
        f.write(f"{t}\n")




