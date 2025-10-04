import stim
import re
import os
from pyzx import *
import matplotlib.pyplot as plt
import time
import argparse
import random

try:
    from tqdm import tqdm
    has_tqdm = True
except ImportError:
    has_tqdm = False


def plot(base_path = "./", save = None, log_scale = False):
    graph_building_times = []
    graph_canonical_times = []
    graph_ur_times = []

    # base_path = "./experiment_elimination/"

    with open(base_path + "/graph_building_times", "r") as f:
        graph_building_times = [float(line.strip()) for line in f.readlines()]

    with open(base_path + "/graph_canonical_times", "r") as f:
        graph_canonical_times = [float(line.strip()) for line in f.readlines()]

    with open(base_path + "/graph_ur_times", "r") as f:
        graph_ur_times = [float(line.strip()) for line in f.readlines()]


    plt.figure(figsize=(10, 6))
    # plt.plot(range(1,len(graph_building_times)+1), graph_building_times, label="To graph state", marker='o')
    plt.plot(range(1,len(graph_building_times)+1), graph_canonical_times, label="To canonical form", marker='s')
    plt.plot(range(1,len(graph_building_times)+1), graph_ur_times, label="To universal representation", marker='^')

    
    # plt.xlim(left=1)
    # plt.xticks(list(range(1, len(graph_building_times) + 1, 20)) + [50])
    # plt.plot(range(len(clifford_simp_times)), clifford_simp_times, label="Clifford Simplification", marker='x')
    plt.xlabel("number of qubits", fontsize=16)
    plt.ylabel("Time (seconds)", fontsize=16)
    plt.title("Performance with * as variable", fontsize=18)
    plt.legend()
    if log_scale:
        plt.gca().set_yscale('log')
    plt.grid(True, alpha=0.3)
    if save != None:
        plt.savefig(base_path + "/" + save, dpi=300)
    else:
        plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, help="Path to the benchmark results")
    parser.add_argument("--save", type=str, help="Save plot")
    parser.add_argument("--log_scale", action="store_true", help="Save plot")
    args = parser.parse_args()


    if args.path == None:
        exit("Insert a path with --path option")
    else:
        plot(args.path, save = args.save, log_scale=args.log_scale)
