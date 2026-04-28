"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { RuntimeRow } from "@/lib/types";

const WARN_SECONDS = 600; // highlight runs that took > 10 min

export function RuntimeChart({ rows }: { rows: RuntimeRow[] }) {
  const data = [...rows]
    .sort((a, b) => (a.run_date < b.run_date ? -1 : 1))
    .map((r) => ({
      ...r,
      dbt_total_runtime_seconds: r.dbt_total_runtime_seconds ?? 0,
    }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="run_date"
          tick={{ fontSize: 11, fill: "#64748b" }}
          tickFormatter={(v: string) => v.slice(5)}
        />
        <YAxis
          tickFormatter={(v: number) =>
            v >= 60 ? `${Math.round(v / 60)}m` : `${v}s`
          }
          tick={{ fontSize: 11, fill: "#64748b" }}
          width={40}
        />
        <Tooltip
          formatter={(v: number) => [
            v >= 60
              ? `${Math.floor(v / 60)}m ${Math.round(v % 60)}s`
              : `${v}s`,
            "Runtime",
          ]}
          labelFormatter={(l: string) => `Date: ${l}`}
        />
        <Bar dataKey="dbt_total_runtime_seconds" radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell
              key={index}
              fill={
                entry.dbt_models_failed > 0
                  ? "#dc2626"
                  : entry.dbt_total_runtime_seconds > WARN_SECONDS
                    ? "#d97706"
                    : "#2563eb"
              }
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
