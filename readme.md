# pyzx_ugrep: Universal Graph Representation for Stabilizer Codes

`pyzx_ugrep` is a Python library designed to convert stabilizer codes into their Universal Graph Representation (UGR) using ZX-calculus. Built on top of `pyzx` and `stim`, this package allows for advanced diagrammatic reasoning, graph state manipulation, and distance computation.

## Web interface

A web interface to interact with the library visually lives in a separate repository: [pyzx_ugrep_web](https://github.com/fradeca01/pyzx_ugrep_web).


## Installation

1. **Clone the repository**:
    ```bash
    git clone https://github.com/fradeca01/pyzx_ugrep.git
    cd pyzx_ugrep
    ```

2. **Create virtual environment**
    ```bash
    python -m venv venv-UGR
    source venv-UGR/bin/activate
    ```

3. **Install the package**
    ```bash
    pip install -e .
    ```

    To also run the notebook and the benchmarks, install the `dev` extras:
    ```bash
    pip install -e ".[dev]"
    ```

4. **Import the package**
    ```python
    from ugr import *
    ```

## Usage and examples

You can generate and visualize examples of universal graph representations in the included `notebook.ipynb` notebook.

Just a quick example, using the five-qubit code, the smallest code that can correct any single-qubit error. Its distance is 3, which is the bound this example finds:

```python
from ugr import stabilizers_to_UGR, distance_upper_bound

# Define your stabilizer code: the [[5,1,3]] five-qubit code
code = ["XZZXI", "IXZZX", "XIXZZ", "ZXIXZ"]

# Convert the code to a Universal Graph Representation
ugr = stabilizers_to_UGR(code)

print("Inputs:", ugr.inputs)
print("Adjacency List:", ugr.adj)
print("Distance Upper Bound:", distance_upper_bound(ugr))
```

