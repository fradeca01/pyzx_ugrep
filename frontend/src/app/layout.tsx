import type { Metadata } from "next";
import { Roboto_Mono } from "next/font/google";
import Header from "@/app/ui/Header";
import Sidebar from "@/app/ui/Sidebar";
import "./globals.css";

import React from "react";

// const geistSans = Geist({
//   variable: "--font-geist-sans",
//   subsets: ["latin"],
// });
// 
// const geistMono = Geist_Mono({
//   variable: "--font-geist-mono",
//   subsets: ["latin"],
// });

export const robotoMono = Roboto_Mono({
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Universal Graph Representation Visualizer",
  description: "Transform stabilizer codes into graph representations and visualize them in 3D.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {


  return (
    <html lang="en" className="overflow-hidden">
      <body
        className={`${robotoMono.className}  antialiase h-screen overflow-hidden bg-secondary`}
      >
        <Header />
        {children}
      </body>
    </html>
  );
}
