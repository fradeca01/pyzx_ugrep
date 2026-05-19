from setuptools import setup, find_packages



setup(
    name="ugr",
    version="0.1.0",
    description="Universal Graph Representation tool based on PyZX",
    packages=find_packages(include=["ugr", "ugr.*"]),

    package_data={
        "ugr": ["*.mzn"],
    },
    
    python_requires=">=3.9",
    install_requires=["typing_extensions>=4.5.0",
                      "numpy>=1.14",
                      "pyperclip>=1.8.1",
                      "tqdm>=4.56.0",
                      "ipywidgets>=7.5",
                      "lark>=1.2.2",
                      "galois>=0.4.7",
                      "stim",
                      "minizinc",
                      "psutil",
                      "pathlib",
                      "pyzx",
                      "fastapi[standard]",
                      "matplotlib",
                      "networkx"
                      ],
    
)