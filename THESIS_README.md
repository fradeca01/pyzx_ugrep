## ⚠️ This is a thesis fork ⚠️

This fork of [PyZX]("https://github.com/zxcalc/pyzx") contains some additions to the Python library, as well as benchmarks and results from my master's thesis. All files are **untouched** from the original repository apart from:
- Some additions inside the `pyzx` package source code (`.\pyzx` folder).
- File and folders specific to my thesis work (`thesis\` folder).

## Additions

The main addition done are the following:
- Added the `graph_states` subpackage ([./pyzx/graph_states.py](https://github.com/fradeca01/pyzx_ugrep/blob/master/pyzx/graph_states.py)), which provides methods to create and work with `graph states` in `pyzx`. 
- Added the `uinversal_representation` subpackage ([./pyzx/universal_representation.py](https://github.com/fradeca01/pyzx_ugrep/blob/master/pyzx/universal_representation.py)), which provides methods to transform a Clifford ZX diagram to its universal representation. 

