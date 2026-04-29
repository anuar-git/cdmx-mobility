"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { api } from "@/lib/api";
import type { ModalLineRow, SubstitutionRow, CorridorRow } from "@/lib/types";
import { MODE_COLORS } from "@/lib/colors";

const CorridorMap = dynamic(() => import("@/components/CorridorMap"), {
  ssr: false,
  loading: () => (
    <div className="h-[420px] bg-slate-800 rounded-xl flex items-center justify-center text-slate-500 text-sm">
      Loading map…
    </div>
  ),
});

function KpiChip({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-slate-800 rounded-lg px-4 py-3 min-w-[120px]">
      <p className="text-xs text-slate-400 uppercase tracking-wide">{label}</p>
      <p className="text-xl font-bold text-white mt-0.5">{value}</p>
    </div>
  );
}

export default function ModalPage() {
  const [lines, setLines] = useState<ModalLineRow[]>([]);
  const [selectedLine, setSelectedLine] = useState<string>("");
  const [substitution, setSubstitution] = useState<SubstitutionRow[]>([]);
  const [corridor, setCorridor] = useState<CorridorRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .modalLines()
      .then(setLines)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selectedLine) return;
    setLoading(true);
    setError(null);
    Promise.all([
      api.modalSubstitution(selectedLine, 90),
      api.modalCorridor(selectedLine),
    ])
      .then(([sub, cor]) => {
        setSubstitution(sub);
        setCorridor(cor);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedLine]);

  const lineInfo = lines.find((l) => l.metro_line === selectedLine);
  const lowServiceDays = substitution.filter((r) => r.is_low_service_day);

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
        {/* Header + picker */}
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <h1 className="text-2xl font-bold">Modal Substitution Explorer</h1>
            <p className="text-slate-400 text-sm mt-1">
              Metro ridership vs. nearby Metrobús &amp; EcoBici — does the alternative mode absorb Metro demand drops?
            </p>
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs text-slate-400 mb-1">Metro line</label>
            <select
              className="w-full bg-slate-800 border border-slate-600 text-slate-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
              value={selectedLine}
              onChange={(e) => setSelectedLine(e.target.value)}
            >
              <option value="">— select a line —</option>
              {lines.map((l) => (
                <option key={l.metro_line} value={l.metro_line}>
                  {l.metro_line} ({l.avg_daily_ridership.toLocaleString()} avg/day)
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && (
          <div className="bg-red-900/40 border border-red-700 text-red-300 rounded-xl px-5 py-4 text-sm">
            {error}
          </div>
        )}

        {lineInfo && (
          <div className="flex flex-wrap gap-3">
            <KpiChip
              label="Avg daily ridership"
              value={lineInfo.avg_daily_ridership.toLocaleString()}
            />
            <KpiChip
              label="Low-service days (30d)"
              value={lineInfo.low_service_days}
            />
            <KpiChip
              label="Nearby Metrobús events/day"
              value={lineInfo.avg_nearby_metrobus_events.toLocaleString()}
            />
            <KpiChip
              label="Nearby EcoBici trips/day"
              value={lineInfo.avg_nearby_ecobici_trips.toLocaleString()}
            />
          </div>
        )}

        {loading && (
          <div className="text-slate-400 text-sm animate-pulse">Loading line data…</div>
        )}

        {selectedLine && !loading && substitution.length > 0 && (
          <>
            {/* Dual-axis substitution chart */}
            <section>
              <h2 className="text-base font-semibold text-slate-300 mb-1">
                Ridership vs. alternative-mode activity (90 days)
              </h2>
              <p className="text-xs text-slate-500 mb-3">
                Orange bars = Metro entries · Lines = nearby Metrobús (red) &amp; EcoBici (green).
                Shaded bars are low-service days (&lt;85% of 7-day avg).
              </p>
              <div className="bg-slate-800 rounded-xl p-5">
                <ResponsiveContainer width="100%" height={300}>
                  <ComposedChart
                    data={substitution}
                    margin={{ top: 4, right: 16, bottom: 0, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis
                      dataKey="service_date"
                      tick={{ fontSize: 10, fill: "#94a3b8" }}
                      tickFormatter={(v: string) => v.slice(5)}
                      interval={13}
                    />
                    <YAxis
                      yAxisId="metro"
                      tick={{ fontSize: 10, fill: "#94a3b8" }}
                      tickFormatter={(v: number) =>
                        v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : `${(v / 1_000).toFixed(0)}K`
                      }
                      width={52}
                    />
                    <YAxis
                      yAxisId="alt"
                      orientation="right"
                      tick={{ fontSize: 10, fill: "#94a3b8" }}
                      tickFormatter={(v: number) =>
                        v >= 1_000 ? `${(v / 1_000).toFixed(0)}K` : String(v)
                      }
                      width={44}
                    />
                    <Tooltip
                      contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                      labelStyle={{ color: "#cbd5e1", fontSize: 11 }}
                      itemStyle={{ fontSize: 11 }}
                      formatter={(v: number, name: string) => [v.toLocaleString(), name]}
                    />
                    <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
                    <Bar
                      yAxisId="metro"
                      dataKey="metro_daily_entries"
                      name="Metro entries"
                      fill={MODE_COLORS.metro.hex}
                      fillOpacity={0.7}
                      radius={[2, 2, 0, 0]}
                    />
                    <Line
                      yAxisId="metro"
                      type="monotone"
                      dataKey="metro_7d_avg"
                      name="7d avg"
                      stroke="#f1f5f9"
                      strokeWidth={1.5}
                      dot={false}
                      strokeDasharray="4 4"
                    />
                    <Line
                      yAxisId="alt"
                      type="monotone"
                      dataKey="nearby_metrobus_events"
                      name="Metrobús events"
                      stroke={MODE_COLORS.metrobus.hex}
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      yAxisId="alt"
                      type="monotone"
                      dataKey="nearby_ecobici_trips"
                      name="EcoBici trips"
                      stroke={MODE_COLORS.ecobici.hex}
                      strokeWidth={2}
                      dot={false}
                    />
                    {lowServiceDays.map((r) => (
                      <ReferenceLine
                        key={r.service_date}
                        x={r.service_date}
                        yAxisId="metro"
                        stroke="#ef4444"
                        strokeOpacity={0.3}
                        strokeWidth={6}
                      />
                    ))}
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </section>

            {/* Corridor map */}
            <section>
              <h2 className="text-base font-semibold text-slate-300 mb-1">
                Corridor map — stations within 300 m
              </h2>
              <p className="text-xs text-slate-500 mb-3">
                Orange = Metro · Red = Metrobús · Green = EcoBici · Arcs connect Metro stops to nearby alternative-mode stations.
              </p>
              <div className="rounded-xl overflow-hidden">
                <CorridorMap data={corridor} height={420} />
              </div>
            </section>
          </>
        )}

        {!selectedLine && !loading && (
          <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
            Select a Metro line above to explore substitution patterns.
          </div>
        )}
      </div>
    </div>
  );
}
