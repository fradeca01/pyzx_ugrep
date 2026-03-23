import stim
from ugr import *
import time
from tqdm import tqdm
import logging

logging.basicConfig(
    filename='minizinc_progress.log',
    level=logging.INFO,
    format='%(asctime)s - n=%(message)s'
)



k = 5
num = 39
iterations = 3

with open("./mzn_times2", 'w') as f:
    for n in tqdm(range(6, num, 1), desc="Testing MiniZinc"):
        total_time = 0
        for i in range(iterations):
            tableau = stim.Tableau.random(n)
            stabilizers = [str(s) for s in tableau.to_stabilizers()]
            ugr = stabilizers_to_UGR(stabilizers[0:n-k])

            start = time.perf_counter()
            a = compute_distance(ugr.inputs, ugr.adj)
            end = time.perf_counter()

            total_time += (end - start)

        avg_time = total_time / iterations

        f.write(f"{n}, {avg_time}\n")
        f.flush()

        logging.info(f"{n} | Avg Time: {avg_time:.4f}s")
