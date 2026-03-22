"use client";

import { useState } from 'react';

type NavLink = {
    name: string;
    href: string;
};

const navLinks: NavLink[] = [
    { name: "From stabilizers", href: "#theme-info" },
    { name: "From graph", href: "#our-team" },
    // { name: "Blog", href: "#blog" },
    // { name: "Style-Guide", href: "#style-guide" },
];

export default function Header() {

    return (
        // 1. Contenitore principale (Header)
        // MODIFICHE CHIAVE:
        // - 'absolute': Rimuove l'header dal flusso normale e lo fa "galleggiare".
        // - 'top-0 left-0': Lo aggancia all'angolo superiore sinistro.
        // - 'z-50': Assicura che stia "sopra" (z-index) al resto del contenuto.
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

                {/* 2. Logo/Titolo (Button) */}
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

                {/* 3. Contenitore Navigazione */}
                {/* <div className="flex items-center space-x-8"> */}

                {/* Nav Links */}
                {/* <nav className="hidden md:flex space-x-8 text-sm font-medium text-gray-700">
                    {navLinks.map((link) => (
                        <a 
                            key={link.name} 
                            href={link.href} 
                            className="hover:text-blue-600 transition duration-150"
                        >
                            {link.name}
                        </a>
                    ))}
                </nav> */}



                {/* Pulsante "Github Link" */}
                <a
                    href="https://github.com/fradeca01/pyzx_ugrep" // Sostituisci con il link di Github
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