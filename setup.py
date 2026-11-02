from setuptools import setup, find_packages



setup(
    name="ugr",
    version="0.1.0",
    description="Universal Graph Representation visualisation toolkit based on PyZX",
    packages=find_packages(include=["ugr", "ugr.*"]),

    package_data={
        "ugr": ["*.mzn"],
    },
    
    python_requires=">=3.9",
    install_requires=["stim",
                      "minizinc",
                      "pyzx"
                      ],

    extras_require={
        "dev": ["tqdm>=4.56.0",
                "matplotlib",
                "networkx"
                ],
    },

)
