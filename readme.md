# pyzx_ugrep: Universal Graph Representation for Stabilizer Codes

`pyzx_ugrep` is a Python library and web tool designed to convert stabilizer codes into their Universal Graph Representation (UGR) using ZX-calculus. Built on top of `pyzx` and `stim`, this package allows for advanced diagrammatic reasoning, graph state manipulation, and distance computation.

## Web interface

A web interface is available to interact with the library visually.

To start it locally `docker` is required. It is sufficient to run the following command from the root of the repository:

```bash
docker compose up
```

If everything worked, the following line should appear in the console:

```bash
frontend-1 | - Local: http://localhost:PORT
```

which indicate the URL to access the web interface,


## Installation

1. **Clone the repository**:
    ```bash
    git clone [this repo]
    cd [repo folder]
    ```

2. **Create virtual environment**
    ```bash
    python -m venv venv-quancom26
    source venv-quancom26/bin/activate
    ```

2. **Install the package**
    ```bash
    pip install -e .
    ```

2. **Import the package**
    ```python
    from ugr import *
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

## UGR QLO reinforcement-learning decoding

The package also includes a Gymnasium environment for the decoding instance of
the quantum-lights-out game on a universal graph representation.

```python
from ugr import QLODecodingEnv, TabularQLODecoder, stabilizers_to_UGR

ugr = stabilizers_to_UGR(["XXI", "IZZ"])

# Syndrome bits are ordered by env.graph.non_pivot_outputs.
env = QLODecodingEnv(ugr, initial_syndrome=[1] * (len(ugr.adj) - 2 * len(ugr.inputs)))
decoder = TabularQLODecoder()

decoder.train(env, episodes=1000, seed=1)
recovery, moves, success = decoder.decode(env, env.initial_syndrome)

print(recovery, moves, success)
```
