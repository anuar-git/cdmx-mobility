"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { IngestionRow } from "@/lib/types";

const SOURCE_COLORS: Record<string, string> = {
  ecobici: "#2563eb",
  metro: "#16a34a",
  metrobus: "#d97706",
  weather: "#7c3aed",
};

const SOURCE_LABELS: Record<string, string> = {
  ecobici: "EcoBici",
  metro: "Metro",
  metrobus: "Metrobús",
  weather: "Weather",
};

interface ChartDatum {
  run_date: string;
  [source: string]: string | number;
}

function pivot(rows: IngestionRow[]): ChartDatum[] {
  const byDate = new Map<string, ChartDatum>();
  for (const row of rows) {
    if (!byDate.has(row.run_date)) {
      byDate.set(row.run_date, { run_date: row.run_date });
    }
    const datum = byDate.get(row.run_date)!;
    datum[row.canonical_source] =
      (datum[row.canonical_source] as number ?? 0) + row.total_rows_ingested;
  }
  return [...byDate.values()].sort((a, b) =>
    a.run_date < b.run_date ? -1 : 1
  );
}

export function RowCountChart({ rows }: { rows: IngestionRow[] }) {
  const data = pivot(rows);
  const sources = [...new Set(rows.map((r) => r.canonical_source))];

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="run_date"
          tick={{ fontSize: 11, fill: "#64748b" }}
          tickFormatter={(v: string) => v.slice(5)}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#64748b" }}
          tickFormatter={(v: number) =>
            v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : v >= 1_000 ? `${(v / 1_000).toFixed(0)}K` : String(v)
          }
          width={48}
        />
        <Tooltip
          formatter={(value: number, name: string) => [
            value.toLocaleString(),
            SOURCE_LABELS[name] ?? name,
          ]}
          labelFormatter={(l: string) => `Date: ${l}`}
        />
        <Legend
          formatter={(value: string) => SOURCE_LABELS[value] ?? value}
          wrapperStyle={{ fontSize: 12 }}
        />
        {sources.map((src) => (
          <Area
            key={src}
            type="monotone"
            dataKey={src}
            stackId="1"
            stroke={SOURCE_COLORS[src] ?? "#94a3b8"}
            fill={SOURCE_COLORS[src] ?? "#94a3b8"}
            fillOpacity={0.6}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
