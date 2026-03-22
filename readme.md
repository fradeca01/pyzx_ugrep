# pyzx_ugrep: Universal Graph Representation for Stabilizer Codes

`pyzx_ugrep` is a Python library and web tool designed to convert stabilizer codes into their Universal Graph Representation (UGR) using ZX-calculus. Built on top of `pyzx` and `stim`, this package allows for advanced diagrammatic reasoning, graph state manipulation, and distance computation.

## Installation

1. **Clone the repository**:
    ```bash
    git clone [this repo]
    cd [repo folder]
    ```

2. **Create virtual environment**
    ```bash
    python -m venv venv-qsw26
    source venv-qsw26/bin/activate
    ```

2. **Install the package**
    ```bash
    pip install -e .
    ```

2. **Import the package**
    ```python
    from ugr as *
    ```

## Usage and examples

You can generate and visualize examples of universal graph representations in the included `notebook.ipynb` notebook.

Just a quick example:

```python
from ugr import stabilizers_to_UGR, distance_upper_bound

# Define your stabilizer code (example)
code = ["XXI", "IZZ"]

# Convert the code to a Universal Graph Representation
ugr = stabilizers_to_UGR(code)

print("Inputs:", ugr.inputs)
print("Adjacency List:", ugr.adj)
print("Distance Upper Bound:", distance_upper_bound(ugr))
```

## Web interface

A web interface is available to interact with the library visually.

The interface is available at the following link: [Hidden]

To start it locally `docker` is required. It is sufficient to run the following command from the root of the repository:

```bash
docker compose up
```
