import stim
import re
import os
from ugr import *
import matplotlib.pyplot as plt
import time
from pyzx.circuit import Circuit
import argparse
import shutil
from tqdm import tqdm


try:
    from tqdm import tqdm
    has_tqdm = True
except ImportError:
    has_tqdm = False


def measure_all(g):
    copy_g = g.copy()
    start = time.perf_counter()
    # print(copy_g)
    inputs = list(copy_g.inputs())
    g2 = GraphState(copy_g)
    end1 = time.perf_counter()
    g2.to_canonical_form(quiet=True)
    end2 = time.perf_counter()
    graph_state_to_ZXCF(g2, inputs)
    end3 = time.perf_counter()

    return (end1 - start, end2 - end1, end3 - end2, end3 - start)


def measure_canonical(g):
    g = GraphState(g)
    time_remove_HS, time_reorder_H = g.benchmark_to_canonical_form()
    return time_remove_HS, time_reorder_H

def stim_qasm_comply(qasm: str) -> str:
    q = qasm
    q = re.sub(r'def\s+rx\(qubit q0\)\s*\{[^}]*\}\n+', '', q)
    q = re.sub(r'rx\s*\(\s*q\[(\d+)\]\s*\)\s*;', r'h q[\1];', q)
    q = re.sub(r'reset\s+q\[(\d+)\];', '', q)
    return q


def save_results(total_times, graph_building_times, graph_canonical_times, graph_ur_times, path = "./"):
    with open(path + "graph_building_times", "w") as f:
        for t in graph_building_times:
            f.write(f"{t}\n")

    with open(path + "graph_canonical_times", "w") as f:
        for t in graph_canonical_times:
            f.write(f"{t}\n")

    with open(path + "graph_ur_times", "w") as f:
        for t in graph_ur_times:
            f.write(f"{t}\n")

    with open(path + "total_times", "w") as f:
        for t in total_times:
            f.write(f"{t}\n")

def generate_instance(n, k, name, method = "graph_state"):
    s = name
    base = "./test_graphs"
    file_path = f"{base}/{s}.qasm"

    def stim_qasm_comply(qasm: str) -> str:
        q = qasm
        q = re.sub(r'def\s+rx\(qubit q0\)\s*\{[^}]*\}\n+', '', q)
        q = re.sub(r'rx\s*\(\s*q\[(\d+)\]\s*\)\s*;', r'h q[\1];', q)
        q = re.sub(r'reset\s+q\[(\d+)\];', '', q)
        return q
    
    qasm_random = ""

    if not os.path.exists(base):
        os.makedirs(base)
    
    if not os.path.exists(file_path):
        # qasm_random = stim.Tableau.random(n).to_circuit(method = method).to_qasm(open_qasm_version=3)
        if method == "elimination":
            qasm_random = stim.Tableau.random(n).to_circuit(method = "elimination").to_qasm(open_qasm_version=3)
        elif method == "graph_state":
            tableau = stim.Tableau.random(n)
            stabilizers = []

            for i in range(k, n):
                stabilizers.append(stim.PauliString(f"Z{i}") * stim.PauliString(n+k))


            for i in range(k):
                stabilizers.append(stim.PauliString(f"Z{i}*Z{i+n}") * stim.PauliString(n+k)) 
                stabilizers.append(stim.PauliString(f"X{i}*X{i+n}") * stim.PauliString(n+k)) 

            state = stim.TableauSimulator()
            state.set_state_from_stabilizers(stabilizers)
            state.do_tableau(tableau, list(range(k, n+k)))
            t = state.current_inverse_tableau().inverse()
            qasm_random = t.to_circuit(method="graph_state").to_qasm(open_qasm_version=3)

        qasm_random = stim_qasm_comply(qasm_random)
        with open(file_path, "w") as f:
            f.write(qasm_random)

def load_instance(n, k, name, method):
    s = name
    file_path = f"./test_graphs/{s}.qasm"
    with open(file_path, "r") as f:
        qasm_random = f.read()
    pyzx_circ = Circuit.from_qasm(qasm_random)
    g = pyzx_circ.to_graph()
    if method == "graph_state":
        input_state = "0"*(n + k)
    else:
        input_state = "0"*(n - k) + "/"*k
    g.apply_state(input_state)
    if method == "graph_state":
        g.set_inputs(g.outputs()[0:k])
    return g

def run_test(i, n, k, num_iteration_per_test = 10, method = "elimination"):
    sum_time_graph = 0.0
    sum_time_canonical = 0.0
    sum_time_ur = 0.0
    sum_total_time = 0.0

    # print(f"Test {i} with n={n}")

    for j in range(num_iteration_per_test):
        s = f"test_{i}_{j}"
        g = load_instance(n, k, s, method = method)
        time_graph, time_canonical, time_ur, total_time = measure_all(g)
        

        sum_time_graph += time_graph
        sum_time_canonical += time_canonical
        sum_time_ur += time_ur
        sum_total_time += total_time

    result_time_graph = sum_time_graph / num_iteration_per_test
    result_time_canonical = sum_time_canonical / num_iteration_per_test
    result_time_ur = sum_time_ur / num_iteration_per_test
    result_total_time = sum_total_time / num_iteration_per_test

    return result_time_graph, result_time_canonical, result_time_ur, result_total_time

def test_n(start_n = 200, k =5, num_tests = 1, num_iteration_per_test = 1, method = "graph_state"):
    

    print(f"Generating {num_tests} random tests ({num_iteration_per_test} iterations per test) starting from {start_n}...")

    for i in tqdm(range(num_tests), desc="Generating tests"):
        n = start_n + i
        # print(f"Generating tests {i} with n={n}")
        for j in range(num_iteration_per_test):
            s = f"test_{i}_{j}"
            generate_instance(n,k, s, method = method)


    print(f"Running benchmark with n as variable and k fixed = 5 random logical qubits...")

    total_times = [] 
    graph_building_times = []
    graph_canonical_times = []
    graph_ur_times = []

    
    
    for i in tqdm(range(num_tests), desc="Benchmarking tests"):

        n = start_n + i

        result_time_graph, result_time_canonical, result_time_ur, result_total_time = run_test(i, n, k, num_iteration_per_test, method)
        graph_building_times.append(result_time_graph)
        graph_canonical_times.append(result_time_canonical)
        graph_ur_times.append(result_time_ur)
        total_times.append(result_total_time)

    save_results(total_times, graph_building_times, graph_canonical_times, graph_ur_times, path = f"./test_n_{method}/")


def test_k(n, num_iteration_per_test = 10, method = "elimination"):
    
    print(f"Generating {n-1} random tests ({num_iteration_per_test} iterations per test) with n = {n}...")

    for i in tqdm(range(n-1), desc="Generating tests"):
        # print(f"Generating tests {i} with n={n}")
        for j in range(num_iteration_per_test):
            s = f"test_{i}_{j}"
            generate_instance(n, i, s, method = method)


    print(f"Running benchmark with fixed n and k =   ranging from 1 to {n-1}")

    total_times = []
    graph_building_times = []
    graph_canonical_times = []
    graph_ur_times = []

    for i in tqdm(range(n-1), desc="Benchmarking tests"):

        k = i + 1
       
        result_time_graph, result_time_canonical, result_time_ur, result_total_time = run_test(i, n, k, num_iteration_per_test, method)

        graph_building_times.append(result_time_graph)
        graph_canonical_times.append(result_time_canonical)
        graph_ur_times.append(result_time_ur)
        total_times.append(result_total_time)



    save_results(total_times, graph_building_times, graph_canonical_times, graph_ur_times, path = "./test_k/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark Universal Representation")
    parser.add_argument("--elimination", action="store_true", help="Plot after benchmarking")
    parser.add_argument("--test_n", action="store_true", help="Plot after benchmarking")
    parser.add_argument("--test_k", action="store_true", help="Plot after benchmarking")
    parser.add_argument("--clean", action="store_true", help="Clean instances")
    # parser.add_argument("--plot", action="store_true", help="Plot after benchmarking")
    args = parser.parse_args()

    if args.elimination:
        method = "elimination"
    else:
        method = "graph_state"

    if args.test_n:
        test_n(start_n = 5, k = 5, method=method, num_tests=50, num_iteration_per_test=5)

    if args.test_k:
        test_k(n = 50, num_iteration_per_test=5, method="elimination")

    if not args.test_n and not args.test_k:
        print("Insert --test_k or --test_n argument or both")

    if args.clean:
        for file_name in os.listdir("./test_graphs/"):
            file_path = os.path.join("./test_graphs/", file_name)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')
