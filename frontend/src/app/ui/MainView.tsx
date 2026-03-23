'use client';

import React, { useState, useEffect, useRef } from "react";
import "@/app/globals.css";

import dynamic from "next/dynamic";

const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), { ssr: false });

interface BackendGraphData {
  inputs: number[];
  adjacency_list: number[][];
  distance_upper_bound: number;
  distance_lower_bound?: number;
  qasmEncoder: string;
}

interface ForceGraphData {
  nodes: { id: number | string; group?: number; }[];
  links: { source: number | string; target: number | string; }[];
}


interface MainViewProps {
  open: boolean;
  setOpen: (open: boolean) => void;
  backendGraphData: BackendGraphData | null;
}

export default function MainView({ open, setOpen, backendGraphData }: MainViewProps) {

  const [graphData, setGraphData] = useState<ForceGraphData>({ nodes: [], links: [] });

  const fgRef = useRef<any>(null);
  const angleRef = useRef(0);

  const defaultSteaneGraph: ForceGraphData = {
    nodes: [
      { id: 0, group: 1 }, { id: 1, group: 1 }, { id: 2, group: 1 },
      { id: 3, group: 1 }, { id: 4, group: 1 }, { id: 5, group: 1 },
      { id: 6, group: 1 }
    ],
    links: [
      { source: 0, target: 1 }, { source: 1, target: 2 }, { source: 0, target: 2 }, // Triangolo 1
      { source: 3, target: 4 }, { source: 4, target: 5 }, { source: 3, target: 5 }, // Triangolo 2
      { source: 0, target: 3 }, { source: 1, target: 4 }, { source: 2, target: 5 }, // Connessioni tra i gruppi
      { source: 6, target: 0 }, { source: 6, target: 2 }, { source: 6, target: 4 }  // Centro connesso
    ]
  };

  useEffect(() => {
    let animationFrameId: number;

    if (backendGraphData) {
      const transformedData = transformBackendData(backendGraphData);
      setGraphData(transformedData);
    } else {
      setGraphData(defaultSteaneGraph);

      const rotate = () => {
        if (fgRef.current) {
          angleRef.current += 0.002; // Velocità rotazione
          const distance = 150; // Distanza dallo zero
          const x = distance * Math.sin(angleRef.current);
          const z = distance * Math.cos(angleRef.current);

          // Aggiorna la camera
          fgRef.current.cameraPosition({ x, z }, null, 0);
        }
        animationFrameId = requestAnimationFrame(rotate);
      };
      rotate();
    }

    // Cleanup
    return () => {
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
    };
  }, [backendGraphData]);

  // Funzione per trasformare i dati dalla lista di adiacenza
  const transformBackendData = (data: BackendGraphData): ForceGraphData => {
    const nodes: { id: number; group?: number }[] = [];
    const links: { source: number; target: number }[] = [];
    const nodeIds = new Set<number>();

    data.adjacency_list.forEach((neighbors, sourceId) => {
      nodeIds.add(sourceId);
      neighbors.forEach(targetId => {
        nodeIds.add(targetId);
        if (sourceId < targetId) {
          links.push({ source: sourceId, target: targetId });
        }
      });
    });

    nodeIds.forEach(id => {
      const isInputNode = data.inputs.includes(id);
      nodes.push({ id: id, group: isInputNode ? 1 : 0 });
    });

    return { nodes, links };
  };


  return (
    <div className="bg-secondary h-full w-full text-white">
      <ForceGraph3D
        ref={fgRef}
        graphData={graphData}
        nodeLabel="id"
        nodeAutoColorBy="group"
        backgroundColor="rgba(0,0,0,0)"
      />
    </div>
  );
}