import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "CDMX Mobility",
  description: "Mexico City mobility analytics — pulse, station, modal, equity, pipeline.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="min-h-screen bg-slate-50">
        <Nav />
        {children}
      </body>
    </html>
  );
}
