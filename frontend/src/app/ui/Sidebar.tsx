"use client";

import { useState, useRef } from 'react';

interface BackendGraphData {
    inputs: number[];
    adjacency_list: number[][];
    distance_upper_bound: number;
    distance_lower_bound?: number;
    qasmEncoder: string;
}

interface SidebarProps {
    isOpen: boolean;
    onOpen: () => void;
    onClose: () => void;
    onGraphDataReceived: (data: BackendGraphData) => void;
}


const InputLabel = ({ title, children }: { title: string, children: React.ReactNode }) => (
    <div className="">
        <label className="block text-sm font-medium text-gray-700 mb-1">
            {title}
        </label>
        {children}
    </div>
);

const exampleNames: Record<string, string> = {
    shor: "Shor Code",
    steane: "Steane Code",
    "5_qubit": "5 Qubits Code",
    r3x3: "Rot Surface (3x3)",
    t2x2: "Toric 2x2",
    t3x3: "Toric 3x3"
};

const inputStyle = "mb-4 w-full text-sm p-2 border border-gray-300 rounded-md shadow-sm focus:border-blue-500";
const buttonStyle = "w-full p-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition";
const secondaryButtonStyle = "p-2 bg-gray-300 text-gray-800 rounded-md hover:bg-gray-300 transition";
const uploadButtonStyle = "w-full py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 transition flex items-center justify-center";


export default function Sidebar({ isOpen, onClose, onGraphDataReceived, onOpen }: SidebarProps) {

    const [selectedExample, setSelectedExample] = useState<string>("");
    const [n, setN] = useState<string>("");
    const [k, setK] = useState<string>("");
    const [currentStep, setCurrentStep] = useState<number>(1);

    const [inputs, setInputs] = useState<number[]>([]);
    const [adjacencyList, setAdjacencyList] = useState<Map<number, Set<number>>>(new Map());

    const [randomStabilizers, setRandomStabilizers] = useState<Boolean>(false);
    const [uploadedStabilizers, setUploadedStabilizers] = useState<Boolean>(false);
    const [uploadedDot, setUploadedDot] = useState<Boolean>(false);
    const [stabilizerValues, setStabilizerValues] = useState<string[]>([]);

    const [isLoading, setIsLoading] = useState<boolean>(false);
    const [progress, setProgress] = useState<number>(0);
    const [estimatedTime, setEstimatedTime] = useState<number | null>(null);
    const [currentJobId, setCurrentJobId] = useState<string | null>(null);
    const [validationError, setValidationError] = useState<string>("");

    const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const stabilizerFileInputRef = useRef<HTMLInputElement>(null);
    const dotFileInputRef = useRef<HTMLInputElement>(null);

    const numN = parseInt(n) || 0;
    const numK = parseInt(k) || 0;

    let stabilizerCount = 0;

    if (numN > numK) {
        stabilizerCount = numN - numK;
    }

    const triggerStabilizerUpload = () => {
        stabilizerFileInputRef.current?.click();
    };

    const triggerDotUpload = () => {
        dotFileInputRef.current?.click();
    };

    const handleStabilizerFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (e) => {
            const content = e.target?.result;
            if (typeof content === 'string') {
                const lines = content
                    .split(/\r?\n/)
                    .map(line => line.trim())
                    .filter(line => line !== '');

                if (lines.length > 0) {
                    setStabilizerValues(lines);
                    const first = lines[0] ?? "";
                    let charCounts = 0
                    for (const ch of first) {
                        if (ch === "I" || ch === "X" || ch === "Y" || ch === "Z") {
                            charCounts += 1
                        }
                    }

                    const n = charCounts
                    const k = (charCounts - lines.length)
                    if (n < k) {
                        setValidationError("Invalid stabilizers: n must be greater than or equal to k.");
                        return;
                    }

                    setN(n.toString())
                    setK(k.toString())
                    setUploadedStabilizers(true);
                    setCurrentStep(2);
                    setValidationError("");
                } else {
                    setValidationError("The file appears to be empty or invalid.");
                }
            }
        };
        reader.readAsText(file);

        event.target.value = '';
    };


    // Funzione helper per convertire la stringa DOT in dati del grafo
    const parseDotToGraph = (dot: string): { inputs: number[], adjacency_list: Map<number, Set<number>> } => {

        const trimmedDot = dot.trim();

        if (!trimmedDot.toLowerCase().startsWith("graph") && !trimmedDot.toLowerCase().startsWith("digraph")) {
            throw new Error("Invalid DOT format: Missing 'graph' or 'digraph' declaration.");
        }
        if (!trimmedDot.includes("{") || !trimmedDot.includes("}")) {
            throw new Error("Invalid DOT format: Missing opening or closing braces.");
        }


        const lines = trimmedDot.split(/\r?\n/);
        const inputs: number[] = [];
        const adjMap = new Map<number, Set<number>>();
        let maxId = -1;

        const addNode = (id: number) => {
            if (!adjMap.has(id)) adjMap.set(id, new Set());
            if (id > maxId) maxId = id;
        };

        lines.forEach(line => {
            line = line.trim();
            if (!line || line.startsWith("graph") || line.startsWith("}") || line.startsWith("layout") || line.startsWith("node")) return;

            const edgeMatch = line.match(/^(\d+)\s*--\s*(\d+)/);
            if (edgeMatch) {
                const u = parseInt(edgeMatch[1], 10);
                const v = parseInt(edgeMatch[2], 10);
                addNode(u);
                addNode(v);
                adjMap.get(u)?.add(v);
                adjMap.get(v)?.add(u);
                return;
            }

            const nodeMatch = line.match(/^(\d+)\s*\[(.*)\]/);
            if (nodeMatch) {
                const id = parseInt(nodeMatch[1], 10);
                const attrs = nodeMatch[2];
                addNode(id);

                if (attrs.includes('label="input"')) {
                    if (!inputs.includes(id)) inputs.push(id);
                }
                return;
            }
        });


        // const adjacency_list: number[][] = [];
        // Riempiamo fino a maxId, gestendo eventuali ID mancanti come array vuoti
        // for (let i = 0; i <= maxId; i++) {
        //     const neighbors = adjMap.get(i);
        //     adjacency_list.push(neighbors ? Array.from(neighbors).sort((a, b) => a - b) : []);
        // }

        if (inputs.length === 0) {
            throw new Error("No input nodes found in the DOT file.");
        }

        if (adjMap.size === 0) {
            throw new Error("No edges found in the DOT file.");
        }

        return { inputs: inputs.sort((a, b) => a - b), adjacency_list: adjMap };
    };

    const handleDotFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (e) => {
            const text = e.target?.result as string;
            // console.log("DOT File Loaded:", text);
            // alert("DOT file loaded (Parsing logic to be implemented)");
            if (!text) { return }

            try {
                console.log("DOT File Loaded...");
                const { inputs, adjacency_list } = parseDotToGraph(text);
                console.log("Parsed Graph Data:", { inputs, adjacency_list });

                setN((adjacency_list.size - inputs.length).toString())
                setK((inputs.length).toString())
                setInputs(inputs);
                setAdjacencyList(adjacency_list);

                setUploadedDot(true);
                setUploadedStabilizers(false)
                setSelectedExample("")
                setCurrentStep(2);
                setValidationError("");
            } catch (error) {
                setValidationError("Error parsing DOT file");
            }
        };
        reader.readAsText(file);
        event.target.value = '';
    };


    const handleNextClick = (random: Boolean) => {
        let stabilizerCount = 0;

        if (selectedExample === "") {
            if (numN <= numK || numN <= 0 || numK <= 0) {
                setValidationError("Insert n > k, they have to be positive integers.");
                return;
            }
            stabilizerCount = numN - numK;

        } else {
        }

        setValidationError("");

        setStabilizerValues(Array(stabilizerCount).fill(""));
        setUploadedStabilizers(false);
        setCurrentStep(2);
        if (random) {
            setRandomStabilizers(true);
        } else {
            setRandomStabilizers(false);
        }
    };


    const handleExampleChange = (value: string) => {
        setSelectedExample(value);
        if (validationError) setValidationError("");
    };
    const handleNChange = (value: string) => {
        setN(value);
        if (validationError) setValidationError("");
    };
    const handleKChange = (value: string) => {
        setK(value);
        if (validationError) setValidationError("");
    };


    const handleStabilizerChange = (index: number, value: string) => {
        const newValues = [...stabilizerValues];
        newValues[index] = value;
        setStabilizerValues(newValues);
    };

    const handleStop = async () => {
        if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
        }

        if (currentJobId) {
            try {
                await fetch(`http://localhost:8000/cancel/${currentJobId}`, {
                    method: "POST"
                });
            } catch (e) {
                console.error("Errore cancellazione job:", e);
            }
        }

        setIsLoading(false);
        setProgress(0);
        setCurrentJobId(null);
    };


    const handleSubmitToBackend = async () => {


        console.log(stabilizerValues)
        if (selectedExample === "" && randomStabilizers === false && !uploadedDot) {
            if (stabilizerValues.length === 0 || stabilizerValues.some(s => s.trim() === "")) {
                setValidationError("Please fill every stabilizer before submitting.");
                return;
            }
            setValidationError("");
        }



        setIsLoading(true);
        setProgress(0);

        const progressTimer = setInterval(() => {
            setProgress((old) => {
                if (old >= 90) return 90;
                return Math.min(old + Math.random() * 5, 90);
            });
        }, 100);

        let dataToSend;

        if (uploadedDot) {
            const payload = Array.from(adjacencyList, ([node, neighbors]) => {
                return [node, Array.from(neighbors)];
            }); dataToSend = {
                inputs: inputs,
                adjacencyList: payload,
            };
        } else {
            dataToSend = {
                selectedExample: selectedExample,
                n: numN,
                k: numK,
                random: randomStabilizers,
                stabilizers: (selectedExample === "" || randomStabilizers === false) ? stabilizerValues : []
            };

        }
        console.log("Invio dati al backend:", JSON.stringify(dataToSend));



        try {

            let startResponse;

            if (uploadedDot) {
                startResponse = await fetch("http://localhost:8000/from_dot", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(dataToSend),
                });
            } else {

                startResponse = await fetch("http://localhost:8000/get_graph", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(dataToSend),
                });
            }
            const startResult = await startResponse.json();

            if (!startResult.success || !startResult.job_id) {
                throw new Error(startResult.error || "Errore avvio job");
            }

            const jobId = startResult.job_id;
            setCurrentJobId(jobId);
            setEstimatedTime(startResult.estimated_time || null);

            console.log("Job avviato con ID:", jobId);

            pollingIntervalRef.current = setInterval(async () => {
                try {
                    const statusResponse = await fetch(`http://localhost:8000/status/${jobId}`);
                    const statusResult = await statusResponse.json();

                    console.log("Job status:", statusResult);

                    if (statusResult.success && statusResult.status != "processing") {
                        // console.log("here")
                        clearInterval(pollingIntervalRef.current!);
                        clearInterval(progressTimer);
                        pollingIntervalRef.current = null;

                        setProgress(100);
                        setTimeout(() => {
                            onGraphDataReceived(statusResult.data);
                            setIsLoading(false);
                            setProgress(0);
                            setCurrentJobId(null);
                        }, 500);
                    }
                    else if (statusResult.success === false) {
                        throw new Error(statusResult.error || "Errore durante il calcolo");
                    }

                } catch (pollError: any) {
                    console.error("Errore polling:", pollError);
                    clearInterval(pollingIntervalRef.current!);
                    clearInterval(progressTimer);
                    alert("Errore: " + pollError.message);
                    setIsLoading(false);
                    setProgress(0);
                }
            }, 500);

        } catch (error: any) {
            console.error("Errore connessione:", error);
            alert("Impossibile avviare il calcolo: " + error.message);
            clearInterval(progressTimer);
            setIsLoading(false);
            setProgress(0);
        }
    };

    const renderCustomStabilizers = () => {
        if (stabilizerValues.length === 0) {
            return (
                <p className="text-sm text-gray-500">
                    Nessuno stabilizzatore da inserire.
                </p>
            );
        }

        return stabilizerValues.map((value, index) => (
            <div key={index} className="flex items-center space-x-2 mb-2">
                <label className="text-sm text-gray-600">S<sub>{index + 1}</sub>:</label>
                <input
                    type="text"
                    className={inputStyle}
                    placeholder={`Stabilizer ${index + 1}`}
                    value={value}
                    onChange={(e) => handleStabilizerChange(index, e.target.value)}
                />
            </div>
        ));
    };

    const handleGoBack = () => {
        setCurrentStep(1);
        setValidationError("");
        setRandomStabilizers(false);
        setUploadedStabilizers(false);
        setUploadedDot(false);
        setStabilizerValues([]);

    }

    const renderStabilizerStep = () => {
        let content;
        let showGenerateButton = true;

        if (randomStabilizers) {
            content = (
                <div>
                    <h3 className="text-lg font-medium">Random code</h3>
                    <p className="text-sm text-gray-600 mt-2">
                        {`Click "Generate graph" to generate a random stabilizer code with parameters n = ${numN} and k = ${numK}.`}
                    </p>
                </div>
            );
        } else if (uploadedStabilizers) {
            content = (
                <div>
                    <h3 className="text-lg font-medium">Uploaded stabilizers</h3>
                    <p className="text-sm text-gray-600 mt-2">
                        {`Click "Generate graph" to generate the stabilizer code:  n = ${numN} and k = ${numK}.`}
                    </p>
                </div>
            );
        } else if (uploadedDot) {
            content = (
                <div>
                    <h3 className="text-lg font-medium">Uploaded DOT</h3>
                    <p className="text-sm text-gray-600 mt-2">
                        {`Click "Generate graph" to generate the stabilizer code:  n = ${numN} and k = ${numK}.`}
                    </p>
                </div>
            );

        } else if (selectedExample) {
            content = (
                <div>
                    <h3 className="text-lg font-medium">{`${exampleNames[selectedExample]}`}</h3>
                    <p className="text-sm text-gray-600 mt-2">
                        {` Click "generate graph" to generate the uiversal representation of the ${exampleNames[selectedExample]}.`}
                    </p>
                </div>
            );
        } else {
            content = (
                <>
                    <p className="mb-6">
                        Insert the code stabilizers:
                    </p>
                    <div>
                        <div className="mt-4 space-y-2">
                            {renderCustomStabilizers()}
                        </div>
                    </div>
                </>
            );
            if (stabilizerValues.length === 0) showGenerateButton = false;

        }
        return (
            <>
                {content}

                {showGenerateButton && (
                    <div className="mt-8">
                        <button
                            onClick={handleSubmitToBackend}
                            className={`${buttonStyle} relative overflow-hidden`}
                            disabled={isLoading}
                        >
                            <span className={isLoading ? "opacity-0" : "opacity-100"}>
                                Generate graph
                            </span>
                            {isLoading && (
                                <span className="absolute inset-0 flex items-center justify-center">
                                    Generating...
                                </span>
                            )}
                        </button>
                        <div className='flex justify-between '>
                            {isLoading && estimatedTime && (
                                <div className="flex items-center justify-center gap-2 mt-4 p-2 bg-white/10 rounded-md">
                                    <svg className="animate-spin h-5 w-5 text-blue-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    <p className="text-sm font-medium text-gray-300">
                                        Generating
                                    </p>
                                </div>
                            )}
                            {isLoading && (
                                <>
                                    {/* <div className="w-full bg-gray-200 rounded-full h-2.5 mt-3 overflow-hidden">
                                    <div
                                        className="bg-blue-400 h-2.5 rounded-full transition-all duration-300 ease-out"
                                        style={{ width: `${progress}%` }}
                                    ></div>
                                </div> */}

                                    <div className="flex justify-center mt-2">
                                        <button
                                            onClick={handleStop}
                                            className="p-2 text-red-500 hover:bg-red-100 rounded-full transition-colors"
                                            title="Stop generation"
                                        >
                                            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" viewBox="0 0 24 24" fill="currentColor">
                                                <path d="M6 6h12v12H6z" />
                                            </svg>
                                        </button>
                                    </div>


                                </>
                            )}
                        </div>

                    </div>
                )}
            </>
        );
    };


    return (
        <>

            {!isOpen && (
                <button
                    onClick={onOpen}
                    className="
                        fixed top-1/5 left-0 
                        z-20 
                        text-white
                        bg-primary
                        p-2 py-4 
                        rounded-md 
                        shadow-lg 
                        transition-all
                        opacity-75 hover:opacity-100
                    "
                >
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-6 w-6"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M13 5l7 7-7 7M5 5l7 7-7 7"
                        />
                    </svg>
                </button>
            )}

            <div
                className={`
                    absolute margin-inline: auto lg:left-0 lg:top-35 lg:bottom-10 w-85 bg-primary shadow-md z-50 h-auto
                    transform transition-transform duration-300 ease-in-out text-white rounded-lg
                    ${isOpen ? 'translate-x-5' : '-translate-x-full'}
                `}
            >
                <div className="flex flex-col items-start h-full overflow-y-auto">
                    <button
                        onClick={onClose}
                        className="hidden lg:display:block opacity-10 mb-6 px-5 pt-5"
                    >
                        <svg
                            xmlns="http://www.w3.org/2000/svg"
                            width="24"
                            height="24"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth="2"
                        >
                            <g transform="scale(-1,1) translate(-24,0)">
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M13 5l7 7-7 7M5 5l7 7-7 7"
                                />
                            </g>
                        </svg>

                    </button>

                    <div className="flex py-5 flex-1 gap-12 overflow-x-hidden overflow-y-scroll flex-col justify-between">

                        <div className="flex-1 flex flex-col ">
                            <h2 className="text-xl px-6 mb-6 font-bold">Insert code stabilizers</h2>
                            <div className={`
                            flex-1
                            items-start
                            flex w-[200%] 
                            transition-transform duration-300 ease-in-out
                            ${currentStep === 1 ? 'translate-x-0' : '-translate-x-1/2'}
                            `}>

                                <div className="w-1/2 flex-shrink h-full flex flex-col px-6 justify-start gap-1">

                                    <p className="mb-4">
                                        Select an example code or insert custom parameters:
                                    </p>

                                    <InputLabel title="Load examples">
                                        <select
                                            value={selectedExample}
                                            onChange={(e) => handleExampleChange(e.target.value)}
                                            className={inputStyle}
                                        >
                                            <option value="">Custom code</option>
                                            <option value="shor">Shor Code</option>
                                            <option value="steane">Steane Code</option>
                                            <option value="5_qubit">5 Qubits Code</option>
                                            <option value="r3x3">rotated_surface_3x3</option>
                                            <option value="t2x2">toric_code_2x2</option>
                                            <option value="t3x3">toric_code_3x3</option>
                                            {/* <option value="custom">Custom</option> */}
                                        </select>
                                    </InputLabel>

                                    {selectedExample === "" || selectedExample === "custom" ? (
                                        <>
                                            <InputLabel title="Value 'n' (physical qubits)">
                                                <input
                                                    type="number"
                                                    min="1"
                                                    value={n}
                                                    onChange={(e) => handleNChange(e.target.value)}
                                                    placeholder="es. 7"
                                                    className={` ${inputStyle}`}
                                                />
                                            </InputLabel>

                                            <InputLabel title="Value 'k' (logical qubits)">
                                                <input
                                                    type="number"
                                                    min="0"
                                                    value={k}
                                                    onChange={(e) => handleKChange(e.target.value)}
                                                    placeholder="es. 1"
                                                    className={inputStyle}
                                                />
                                            </InputLabel>
                                        </>
                                    ) : (

                                        <p className="text-sm text-gray-600">
                                            The values 'n' and 'k' for the {exampleNames[selectedExample]} are predefined.
                                        </p>
                                    )}

                                    {validationError && (
                                        <p className="text-red-600 text-sm mt-6">
                                            {validationError}
                                        </p>
                                    )
                                    }

                                    <button onClick={() => handleNextClick(false)} className={`${buttonStyle} mt-6`}>
                                        Next &rarr;
                                    </button>


                                    {(selectedExample === "") && (
                                        <>
                                            <button onClick={() => handleNextClick(true)} className={`${buttonStyle} mt-6`}>
                                                Generate random &rarr;
                                            </button>

                                            <div className="overflow-x-hidden">
                                                <button
                                                    onClick={triggerStabilizerUpload}
                                                    className={`${uploadButtonStyle} mt-6`}
                                                    type="button"
                                                >
                                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                                                    </svg>
                                                    Upload stabilizers
                                                </button>
                                                <input
                                                    type="file"
                                                    accept=""
                                                    ref={stabilizerFileInputRef}
                                                    className='hidden'
                                                    onChange={handleStabilizerFileUpload}
                                                />
                                                <p className="text-xs text-gray-400 mt-2 text-center">
                                                    File should contain one stabilizer per line (e.g., XZZX)
                                                </p>
                                            </div>

                                            <div className="">

                                                <button
                                                    onClick={triggerDotUpload}
                                                    className={`${uploadButtonStyle} mt-6`}
                                                    type="button"
                                                >
                                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                                                    </svg>
                                                    Upload DOT file
                                                </button>
                                                <input
                                                    type="file"
                                                    accept=".dot"
                                                    ref={dotFileInputRef}
                                                    className='hidden'
                                                    onChange={handleDotFileUpload}
                                                />
                                                <p className="text-xs text-gray-400 text-center mt-2">
                                                    File should contain a valid DOT representation of the graph. Input nodes must be labeled with label="input".
                                                </p>
                                            </div>
                                        </>
                                    )
                                    }


                                </div>
                                <div className="w-1/2 px-6 flex-shrink-0">
                                    <button onClick={() => handleGoBack()} className={`${secondaryButtonStyle} text-sm font-semibold mb-4 text-left`}>
                                        &larr; Back
                                    </button>

                                    {renderStabilizerStep()}

                                    {validationError && (
                                        <p className="text-red-600 text-sm mt-2">
                                            {validationError}
                                        </p>
                                    )
                                    }
                                </div>

                            </div>
                        </div>
                    </div>
                </div>
            </div >

        </>
    );
}