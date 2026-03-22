"use client";

import { useState, useEffect, useRef } from 'react';

interface BackendGraphData {
    inputs: number[];
    adjacency_list: number[][];
    distance_upper_bound: number;
    distance_lower_bound?: number;
    qasmEconder?: string;
}


interface PropertyBarProps {
    isOpen: boolean;
    onOpen: () => void;
    onClose: () => void;
    onOpenEncoder: () => void;
    backendGraphData: BackendGraphData | null;
}


const InputLabel = ({ title, children }: { title: string, children: React.ReactNode }) => (
    <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-1">
            {title}
        </label>
        {children}
    </div>
);

const buttonStyle = "w-full p-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition";
const outlineButtonStyle = "w-full p-2 border border-blue-600 text-blue-600 rounded-md hover:bg-blue-50 transition flex items-center justify-center gap-2";

export default function PropertyBar({ isOpen, onClose, onOpen, onOpenEncoder, backendGraphData }: PropertyBarProps) {

    const [isComputing, setIsComputing] = useState(false);
    const [estimatedTime, setEstimatedTime] = useState<number | null>(null);
    const [computedLowerBound, setComputedLowerBound] = useState<string | number | null>(null);
    const pollInterval = useRef<NodeJS.Timeout | null>(null);

    const [currentJobId, setCurrentJobId] = useState<string | null>(null);


    useEffect(() => {
        setComputedLowerBound(null);
        setEstimatedTime(null);
        setIsComputing(false);
        if (pollInterval.current) clearInterval(pollInterval.current);
    }, [backendGraphData]);

    const generateDotString = (data: BackendGraphData): string => {
        const inputsSet = new Set(data.inputs);
        let dot = "graph G {\n";
        dot += '  layout=neato;\n';
        dot += '  node [style=filled];\n';

        data.adjacency_list.forEach((_, id) => {
            const isInput = inputsSet.has(id);
            const inputLabel = isInput ? "label=\"input\"" : "";
            const color = isInput ? "lightblue" : "lightgrey";
            const shape = isInput ? "box" : "circle";
            dot += `  ${id} [${inputLabel}, fillcolor="${color}", shape="${shape}"];\n`;
        });

        data.adjacency_list.forEach((neighbors, source) => {
            neighbors.forEach((target) => {
                if (source < target) {
                    dot += `  ${source} -- ${target};\n`;
                }
            });
        });

        dot += "}";
        return dot;
    };

    const handleDownloadDot = () => {
        if (!backendGraphData) return;

        const dotString = generateDotString(backendGraphData);
        const blob = new Blob([dotString], { type: 'text/vnd.graphviz' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = 'graph_representation.dot';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const handleComputeClick = async () => {
        if (!backendGraphData) return;

        setIsComputing(true);
        setComputedLowerBound(null);
        setEstimatedTime(null);

        try {
            const response = await fetch("http://localhost:8000/solve", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    inputs: backendGraphData.inputs,
                    adjacency_list: backendGraphData.adjacency_list
                })
            });

            const result = await response.json();

            if (!result.success) {
                alert("Errore avvio solver: " + result.error);
                setIsComputing(false);
                return;
            }

            const jobId = result.job_id;
            setCurrentJobId(jobId);
            setEstimatedTime(result.estimated_time);

            pollInterval.current = setInterval(async () => {
                try {
                    const statusRes = await fetch(`http://localhost:8000/status/${jobId}`);
                    const statusData = await statusRes.json();

                    console.log("Polling status:", statusData);

                    if (statusData.status != "processing" && statusData.success === true) {
                        setComputedLowerBound(statusData.data);
                        setIsComputing(false);
                        clearInterval(pollInterval.current!);
                    } else if (statusData.status != "processing" && statusData.success === false) {
                        alert("Errore solver: " + statusData.error);
                        setIsComputing(false);
                        clearInterval(pollInterval.current!);
                    }
                } catch (e) {
                    console.error("Polling error", e);
                }
            }, 1000);

        } catch (e) {
            console.error(e);
            setIsComputing(false);
            alert("Errore di connessione");
        }
    };

    const handleStop = async () => {
        if (pollInterval.current) {
            clearInterval(pollInterval.current);
            pollInterval.current = null;
        }

        if (currentJobId) {
            try {
                await fetch(`http://localhost:8000/cancel/${currentJobId}`, {
                    method: "POST"
                });
                console.log("Job cancellato lato server");
            } catch (e) {
                console.error("Errore cancellazione job:", e);
            }
        }

        setIsComputing(false);
        setCurrentJobId(null);
    };


    return (
        <>
            {!isOpen && (
                <button
                    onClick={onOpen}
                    className="fixed top-1/5 right-0 -translate-y-1/2 z-20 text-white bg-primary p-2 py-4 rounded-md shadow-lg transition-all opacity-75 hover:opacity-100"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7M18 19l-7-7 7-7" />
                    </svg>
                </button>
            )}

            <div className={`absolute right-0 top-35 bottom-10 w-85 bg-primary shadow-md z-50 h-auto transform transition-transform duration-300 ease-in-out text-white rounded-lg ${isOpen ? '-translate-x-5' : 'translate-x-full'}`}>
                <div className="px-5 py-5 h-full overflow-y-auto">
                    <button onClick={onClose} className="text-xl opacity-10 mb-4">
                        <svg
                            xmlns="http://www.w3.org/2000/svg"
                            width="24"
                            height="24"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth="2"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M13 5l7 7-7 7M5 5l7 7-7 7"
                            />
                        </svg>
                    </button>

                    <div className="flex flex-col justify-start">
                        <h2 className="text-xl font-semibold mb-10">Code properties</h2>

                        <div className='mb-10'>
                            <h3 className="text-md font-medium">Distance upper bound</h3>
                            <p className="text-sm text-gray-600 mt-2">
                                {backendGraphData?.distance_upper_bound ?? "-"}
                            </p>
                        </div>
                        <div className='mb-10'>
                            <h3 className="text-md font-medium">Exact Distance</h3>

                            <p className="text-sm text-gray-600 mt-2 mb-4 font-mono ">
                                {computedLowerBound !== null ? computedLowerBound : ""}
                            </p>

                            {!computedLowerBound && (
                                <button
                                    onClick={handleComputeClick}
                                    disabled={isComputing || !backendGraphData}
                                    className={buttonStyle}
                                >
                                    {isComputing ? "Computing..." : "Compute (MiniZinc)"}
                                </button>
                            )}

                            <div className='flex justify-between '>


                                {isComputing && estimatedTime && (
                                    <div className="flex items-center justify-center gap-2 mt-4 p-2 bg-white/10 rounded-md">
                                        <svg className="animate-spin h-5 w-5 text-blue-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                        </svg>
                                        <p className="text-sm font-medium text-gray-300">
                                            Computing, may take a long time.
                                        </p>
                                    </div>
                                )}
                                {isComputing && (
                                    <>
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


                        <div className='mb-10'>
                            <h3 className="text-md font-medium mb-5">Exports</h3>
                            <div className="flex flex-col gap-3">

                                <button
                                    onClick={handleDownloadDot}
                                    disabled={!backendGraphData}
                                    className={`${outlineButtonStyle} border-white text-white hover:bg-white/10`}
                                    title="Download GraphViz DOT file"
                                >
                                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
                                    </svg>
                                    Download DOT
                                </button>
                            </div>
                        </div>

                        <div className='mb-10'>
                            <h3 className="text-md font-medium mb-5">Code encoder</h3>
                            <button onClick={onOpenEncoder} className={`${buttonStyle} flex items-center justify-center gap-2`}>
                                View Circuit
                            </button>
                        </div>

                    </div>
                </div>
            </div>
        </>
    );
}