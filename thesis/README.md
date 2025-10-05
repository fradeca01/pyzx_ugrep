# Thesis results

This folder contains the experiments, configurations, and results for my thesis:
*"Implementation through ZX
calculus of a universal
representation for stabilizer codes"*, [University of Udine, 2024/2025].

## How to install local package
1. Clone the repository:
    ```bash
    git clone https://github.com/fradeca01/pyzx_ugrep.git 
    ```


2. Create a virtual environment (to avoid conflicts with original repo)

    ```bash
    python -m venv venv-thesis
    source venv-thesis/bin/activate
    ```

2. Install dependencies (from repo root):
   ```bash
   pip install -r requirements.txt
   ```


## How to run benchmarks

1. Move to `thesis/benchamarks` folder
2. Run `benchmark_universal.py` script, the following arguments are available:
    - `--test_n`: run the benchmark with the number of physical qubits as variable using the same parameters as Chapter 5 of my thesis.
    - `--test_k`: run the benchmark with the number of logical qubits as variable using the same parameters as Chapter 5 of my thesis
    - `--clean`: delete all test instances after a succesfull run

    At least one of `--test_n` or `--test_k` is mandatory. It is also possible to change the parameters by modifying the `main`  function of this script. 

3. To plot the results it is possible to use the `benchmarks/plot.py` script. This script plots the results from `benchmark_universal.py` script. The following arguments are available:
    - `--path`: Mandatory. The path where results from `benchmark_universal.py` are stored.
    - `--log_scale`: to use logarithmic scale on $y$ axis.
    - `--save`: the path to save the plot.

## Examples

It is possible to generate some examples of universal graph representations in the `graph_state.ipynb` notebook.


## Graphical interface

To access the graphical interface to transform a stabilzer code to its universal represetntation visit the following: [Link](https://universal-graph-repr.streamlit.app/)


