"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const LINKS = [
  { href: "/pulse", label: "Pulse" },
  { href: "/station", label: "Station" },
  { href: "/modal", label: "Modal" },
  { href: "/equity", label: "Equity" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="bg-slate-900 border-b border-slate-700 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 flex items-center gap-1 h-12">
        <span className="text-white font-bold text-sm mr-6 shrink-0">
          CDMX Mobility
        </span>
        {LINKS.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              "px-3 py-1.5 rounded text-sm transition-colors",
              pathname.startsWith(href)
                ? "bg-slate-700 text-white font-medium"
                : "text-slate-400 hover:text-white hover:bg-slate-800"
            )}
          >
            {label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
