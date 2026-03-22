"use client";

import React, { useMemo } from "react";

// --- Tipi per il nostro parser interno ---
interface Gate {
    type: string;
    qubits: number[]; // Indici dei qubit coinvolti
    controls?: number[]; // Indici dei controlli (per CX, CZ)
    params?: string;
}

interface ParsedCircuit {
    numQubits: number;
    columns: Gate[][]; // Organizziamo il circuito in colonne temporali
}

// --- Funzioni di Parsing ---
const parseQASM = (qasm: string): ParsedCircuit => {
    const lines = qasm.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('//') && !l.startsWith('OPENQASM') && !l.startsWith('include'));

    let numQubits = 0;
    const gates: Gate[] = [];

    // Regex semplici per individuare i comandi
    const qregRegex = /qreg\s+\w+\[(\d+)\];/;
    const gateRegex = /(\w+)\s+([^;]+);/;

    lines.forEach(line => {
        // 1. Trova il numero di qubit
        const qregMatch = line.match(qregRegex);
        if (qregMatch) {
            numQubits = Math.max(numQubits, parseInt(qregMatch[1], 10));
            return;
        }

        // 2. Analizza le porte
        const match = line.match(gateRegex);
        if (match) {
            const type = match[1].toLowerCase();
            const args = match[2].split(',').map(s => s.trim());

            // Estrai indici qubit (es. "q[0]" -> 0)
            const indices = args.map(arg => {
                const idxMatch = arg.match(/\[(\d+)\]/);
                return idxMatch ? parseInt(idxMatch[1], 10) : 0;
            });

            // Gestione porte specifiche
            if (type === 'cx') {
                gates.push({ type: 'X', qubits: [indices[1]], controls: [indices[0]] });
            } else if (type === 'cz') {
                gates.push({ type: 'Z', qubits: [indices[1]], controls: [indices[0]] });
            } else if (['h', 'x', 'y', 'z', 's', 't', 'tdg'].includes(type)) {
                gates.push({ type: type.toUpperCase(), qubits: [indices[0]] });
            } else if (type === 'measure') {
                const measureSource = args[0].match(/\[(\d+)\]/);
                if (measureSource) {
                    gates.push({ type: 'M', qubits: [parseInt(measureSource[1], 10)] });
                }
            }
        }
    });

    // Fallback se non c'è qreg
    if (numQubits === 0 && gates.length > 0) {
        numQubits = Math.max(...gates.flatMap(g => [...g.qubits, ...(g.controls || [])])) + 1;
    }

    // 3. Organizza in colonne
    const columns: Gate[][] = gates.map(g => [g]);

    return { numQubits, columns };
};
interface BackendGraphData {
    inputs: number[];
    adjacency_list: number[][];
    distance_upper_bound: number;
    distance_lower_bound?: number;
    qasmEncoder: string;
}

// --- Componente Principale ---
interface CircuitDrawerProps {
    isOpen: boolean;
    onClose: () => void;
    qasmData: BackendGraphData | null;
}

export default function CircuitDrawer({ isOpen, onClose, qasmData }: CircuitDrawerProps) {

    const circuit = useMemo(() => {
        if (!qasmData) return null;
        try {
            return parseQASM(qasmData.qasmEncoder || "");
        } catch (e) {
            console.error("Parsing error", e);
            return null;
        }
    }, [qasmData]);

    // Costanti grafiche
    const ROW_H = 40;
    const COL_W = 40;
    const START_X = 60;
    const START_Y = 40;

    // if (!isOpen) return null;

    const handleDownload = () => {
        if (!qasmData?.qasmEncoder) return;
        const blob = new Blob([qasmData.qasmEncoder], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'circuit.qasm';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    return (
        <>
            {/* Overlay */}
            {/* Modifica questo blocco nel tuo return */}
            <div
                onClick={onClose}
                className={`
        fixed inset-0 bg-black/50 z-40 transition-opacity duration-300
        ${isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}
    `}
            />

            {/* Drawer Panel */}
            <div
                className={`
                    fixed bottom-0 left-0 right-0 
                    h-[500px] md:h-[600px] 
                    bg-secondary text-white 
                    shadow-[0_-4px_20px_rgba(0,0,0,0.5)] 
                    z-50 
                    rounded-t-2xl
                    flex flex-col border-t border-white/10
                    transform transition-transform duration-300 ease-in-out
                    ${isOpen ? 'translate-y-0' : 'translate-y-full'}
                `}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 shrink-0 bg-primary rounded-t-2xl">
                    <h2 className="text-xl font-semibold font-mono">Quantum Circuit</h2>

                    <div className="flex items-center gap-2">
                        {/* Download Button */}
                        <button
                            onClick={handleDownload}
                            disabled={!qasmData}
                            className="p-2 hover:bg-white/10 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            title="Download QASM"
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                        </button>

                        {/* Close Button */}
                        <button
                            onClick={onClose}
                            className="p-2 hover:bg-white/10 rounded-full transition-colors"
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                </div>

                {/* Circuit Visualization Area */}
                <div className="flex-1 overflow-auto p-8 relative bg-[#0B1221]">

                    {!circuit || circuit.numQubits === 0 ? (
                        <div className="text-gray-400 text-center mt-10">
                            {qasmData ? "Unable to parse circuit." : "No QASM data available."}
                        </div>
                    ) : (
                        <svg
                            width={Math.max(800, START_X + circuit.columns.length * COL_W + 100)}
                            height={Math.max(200, START_Y + circuit.numQubits * ROW_H)}
                            className="mx-auto"
                        >
                            {/* 1. Disegna le linee dei Qubit (Wires) */}
                            {Array.from({ length: circuit.numQubits }).map((_, i) => (
                                <g key={`wire-${i}`}>
                                    <text
                                        x={10}
                                        y={START_Y + i * ROW_H + 5}
                                        fill="#9CA3AF"
                                        fontSize="14"
                                        fontFamily="monospace"
                                    >
                                        q[{i}]
                                    </text>
                                    <line
                                        x1={START_X}
                                        y1={START_Y + i * ROW_H}
                                        x2={START_X + circuit.columns.length * COL_W + 40}
                                        y2={START_Y + i * ROW_H}
                                        stroke="#4B5563"
                                        strokeWidth="2"
                                    />
                                </g>
                            ))}

                            {/* 2. Disegna le porte */}
                            {circuit.columns.map((col, colIdx) => {
                                const x = START_X + colIdx * COL_W + (COL_W / 2);

                                return col.map((gate, gateIdx) => {
                                    const y = START_Y + gate.qubits[0] * ROW_H;

                                    // --- Porte a singolo Qubit ---
                                    if (!gate.controls) {
                                        if (gate.type === 'M') {
                                            return (
                                                <g key={`gate-${colIdx}-${gateIdx}`}>
                                                    <rect
                                                        x={x - 15} y={y - 15} width={30} height={30}
                                                        fill="#1F2937" stroke="#F87171" strokeWidth="2" rx="4"
                                                    />
                                                    <text x={x} y={y + 5} textAnchor="middle" fill="#F87171" fontSize="12" fontWeight="bold">M</text>
                                                </g>
                                            );
                                        } else {
                                            const color = gate.type === 'X' ? '#34D399' : gate.type === 'H' ? '#60A5FA' : '#A78BFA';
                                            return (
                                                <g key={`gate-${colIdx}-${gateIdx}`}>
                                                    <rect
                                                        x={x - 15} y={y - 15} width={30} height={30}
                                                        fill="#1F2937" stroke={color} strokeWidth="2" rx="4"
                                                    />
                                                    <text x={x} y={y + 5} textAnchor="middle" fill={color} fontSize="14" fontWeight="bold">{gate.type}</text>
                                                </g>
                                            );
                                        }
                                    }

                                    // --- Porte Controllate (CX, CZ) ---
                                    if (gate.controls) {
                                        const yControl = START_Y + gate.controls[0] * ROW_H;
                                        const yTarget = y;

                                        return (
                                            <g key={`cgate-${colIdx}-${gateIdx}`}>
                                                {/* Linea verticale di collegamento */}
                                                <line x1={x} y1={yControl} x2={x} y2={yTarget} stroke="#9CA3AF" strokeWidth="2" />

                                                {/* Pallino di controllo (Controllo) */}
                                                <circle cx={x} cy={yControl} r={6} fill="#9CA3AF" />

                                                {/* Target Visualization */}
                                                {gate.type === 'X' ? (
                                                    // CNOT: Cerchio con +
                                                    <g>
                                                        <circle cx={x} cy={yTarget} r={12} fill="#1F2937" stroke="#9CA3AF" strokeWidth="2" />
                                                        <line x1={x} y1={yTarget - 8} x2={x} y2={yTarget + 8} stroke="#9CA3AF" strokeWidth="2" />
                                                        <line x1={x - 8} y1={yTarget} x2={x + 8} y2={yTarget} stroke="#9CA3AF" strokeWidth="2" />
                                                    </g>
                                                ) : gate.type === 'Z' ? (
                                                    // CZ: Altro pallino (Simmetrico)
                                                    <circle cx={x} cy={yTarget} r={6} fill="#9CA3AF" />
                                                ) : (
                                                    // Altre controllate generiche: Box
                                                    <g>
                                                        <rect
                                                            x={x - 15} y={yTarget - 15} width={30} height={30}
                                                            fill="#1F2937" stroke="#A78BFA" strokeWidth="2" rx="4"
                                                        />
                                                        <text x={x} y={yTarget + 5} textAnchor="middle" fill="#A78BFA" fontSize="12" fontWeight="bold">{gate.type}</text>
                                                    </g>
                                                )}
                                            </g>
                                        );
                                    }
                                    return null;
                                });
                            })}
                        </svg>
                    )}
                </div>

                {/* <div className="p-2 border-t border-white/10 text-xs text-gray-500 text-center bg-primary shrink-0">
                    Native React SVG Renderer
                </div> */}
            </div>
        </>
    );
}