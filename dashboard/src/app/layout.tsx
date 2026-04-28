import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CDMX Mobility — Pipeline Health",
  description: "Observability dashboard for the cdmx-mobility data pipeline.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50">{children}</body>
    </html>
  );
}
