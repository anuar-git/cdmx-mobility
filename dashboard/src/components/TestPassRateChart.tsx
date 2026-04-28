"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { TestsRow } from "@/lib/types";

export function TestPassRateChart({ rows }: { rows: TestsRow[] }) {
  const data = [...rows].sort((a, b) =>
    a.run_date < b.run_date ? -1 : 1
  );

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="run_date"
          tick={{ fontSize: 11, fill: "#64748b" }}
          tickFormatter={(v: string) => v.slice(5)}
        />
        <YAxis
          domain={[0, 100]}
          tickFormatter={(v: number) => `${v}%`}
          tick={{ fontSize: 11, fill: "#64748b" }}
          width={44}
        />
        <Tooltip
          formatter={(v: number, name: string) => [
            name === "dbt_test_pass_rate_pct" ? `${v?.toFixed(1)}%` : v,
            name === "dbt_test_pass_rate_pct" ? "Pass rate" : name,
          ]}
          labelFormatter={(l: string) => `Date: ${l}`}
        />
        {/* 100% reference line — any drop is immediately visible */}
        <ReferenceLine y={100} stroke="#16a34a" strokeDasharray="4 4" />
        <Line
          type="stepAfter"
          dataKey="dbt_test_pass_rate_pct"
          stroke="#2563eb"
          strokeWidth={2}
          dot={{ r: 3, fill: "#2563eb" }}
          activeDot={{ r: 5 }}
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
