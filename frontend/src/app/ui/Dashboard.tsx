'use client';

import "@/app/globals.css";
import React, { useState } from "react";
import Sidebar from "@/app/ui/Sidebar";
import PropertyBar from "@/app/ui/PropertyBar";
import MainView from "@/app/ui/MainView";
import CircuitDrawer from "@/app/ui/CircuitDrawer"; 

interface BackendGraphData {
    inputs: number[];
    adjacency_list: number[][];
    distance_upper_bound: number;
    distance_lower_bound?: number;
    qasmEncoder: string;
}

export default function Home() {
    const [open, setOpen] = useState(true);
    const [isSidebarOpen, setSidebarOpen] = useState<boolean>(true);
    const [isRightSidebarOpen, setRightSidebarOpen] = useState<boolean>(false);
    const [backendGraphData, setBackendGraphData] = useState<BackendGraphData | null>(null);

    const graphInserted = (data: BackendGraphData | null) => {
        setBackendGraphData(data);
        setRightSidebarOpen(true);
    }



    const [isCircuitDrawerOpen, setCircuitDrawerOpen] = useState<boolean>(false);

    return (

        <div className="flex h-ful flex-row justify-start items-center">
            {/* <Sidebar open = {open} setOpen={setOpen} />    */}
            <Sidebar
                isOpen={isSidebarOpen}
                onClose={() => setSidebarOpen(false)}
                onOpen={() => setSidebarOpen(true)}
                onGraphDataReceived={graphInserted}
            />
            <PropertyBar
                isOpen={isRightSidebarOpen}
                onClose={() => setRightSidebarOpen(false)}
                onOpen={() => setRightSidebarOpen(true)}
                backendGraphData={backendGraphData}
                onOpenEncoder={() => setCircuitDrawerOpen(true)}
            />
            <MainView open={open} setOpen={setOpen} backendGraphData={backendGraphData} />
            <CircuitDrawer
                isOpen={isCircuitDrawerOpen}
                onClose={() => setCircuitDrawerOpen(false)}
                qasmData={backendGraphData}
            />
        </div>

    )
}