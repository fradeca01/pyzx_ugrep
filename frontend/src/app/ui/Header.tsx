"use client";

import { useState } from 'react';

type NavLink = {
    name: string;
    href: string;
};

const navLinks: NavLink[] = [
    { name: "From stabilizers", href: "#theme-info" },
    { name: "From graph", href: "#our-team" },
];

export default function Header() {

    return (

        <>
            <header className="
            absolute 
            h-20
            top-2 left-5 right-5
            my-5 
            bg-primary 
            flex items-center justify-between 
            text-black 
            shadow-md  
            px-5
            z-50
            rounded-lg
        ">


                <button
                    onClick={() => window.location.reload()}
                    className="
                        text-md
                        lg:text-2xl 
                        font-bold 
                        text-white 
                        hover:text-gray-200 
                        transition 
                        duration-200 
                        ease-in-out
                        focus:outline-none
                        cursor-pointer
                    "
                    title="Reload Page"
                >
                    Universal Graph Representation visualizer
                </button>





                <a
                    href=""
                    target="_blank"
                    className="
                        bg-blue-600 
                        hover:bg-blue-700 
                        text-white 
                        font-medium 
                        py-2 
                        px-6 
                        rounded-md 
                        shadow-lg 
                        transition 
                        duration-300 
                        ease-in-out
                        whitespace-nowrap
                    "
                >
                    Github
                </a>
                {/* </div> */}
            </header>
        </>
    );
}