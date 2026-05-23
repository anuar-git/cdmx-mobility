"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
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
import { api } from "@/lib/api";
import type { AccessibilityRow, StockoutByBoroughRow, BoroughSummary } from "@/lib/types";

const EquityMap = dynamic(() => import("@/components/EquityMap"), {
  ssr: false,
  loading: () => (
    <div className="h-[480px] bg-slate-800 rounded-xl flex items-center justify-center text-slate-500 text-sm">
      Loading map…
    </div>
  ),
});

interface GeoFeature {
  type: "Feature";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  geometry: any;
  properties: { borough: string; [key: string]: unknown };
}

interface GeoJSON {
  type: string;
  features: GeoFeature[];
}

function scoreGradient(score: number, min: number, max: number): string {
  const t = max > min ? (score - min) / (max - min) : 0.5;
  const r = Math.round(200 - t * 160);
  const g = Math.round(40 + t * 160);
  return `rgb(${r},${g},80)`;
}

export default function EquityPage() {
  const [scores, setScores] = useState<AccessibilityRow[]>([]);
  const [stockout, setStockout] = useState<StockoutByBoroughRow[]>([]);
  const [geojson, setGeojson] = useState<GeoJSON | null>(null);
  const [boroughs, setBoroughs] = useState<BoroughSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.equityScores(),
      api.equityStockoutByBorough(30),
      fetch("/alcaldias.geojson").then((r) => r.json() as Promise<GeoJSON>),
    ])
      .then(([sc, so, gj]) => {
        setScores(sc);
        setStockout(so);
        setGeojson(gj);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  // Compute borough summaries once geojson + scores are loaded
  useEffect(() => {
    if (!geojson || !scores.length) return;

    Promise.all([
      import("@turf/boolean-point-in-polygon"),
      import("@turf/helpers"),
    ])
      .then(([boolMod, helpersMod]) => {
        const booleanPointInPolygon = boolMod.default;
        const { point } = helpersMod;

        // Build stockout lookup keyed by station_id
        const soByStation = new Map(stockout.map((s) => [s.station_id, s.avg_stockout_minutes]));

        const byBorough = new Map<
          string,
          { scoreSum: number; scoreCount: number; stockoutSum: number; stockoutCount: number }
        >();

        for (const s of scores) {
          const pt = point([s.lon, s.lat]);
          for (const f of geojson.features) {
            if (booleanPointInPolygon(pt, f)) {
              const b = f.properties.borough;
              const cur = byBorough.get(b) ?? {
                scoreSum: 0,
                scoreCount: 0,
                stockoutSum: 0,
                stockoutCount: 0,
              };
              const so = soByStation.get(s.station_id) ?? 0;
              byBorough.set(b, {
                scoreSum: cur.scoreSum + s.accessibility_score,
                scoreCount: cur.scoreCount + 1,
                stockoutSum: cur.stockoutSum + so,
                stockoutCount: cur.stockoutCount + (so > 0 ? 1 : 0),
              });
              break;
            }
          }
        }

        const result: BoroughSummary[] = Array.from(byBorough.entries())
          .map(([borough, agg]) => ({
            borough,
            avg_score: agg.scoreCount ? agg.scoreSum / agg.scoreCount : 0,
            station_count: agg.scoreCount,
            avg_stockout_minutes: agg.stockoutCount
              ? agg.stockoutSum / agg.stockoutCount
              : 0,
          }))
          .sort((a, b) => b.avg_score - a.avg_score);

        setBoroughs(result);
      })
      .catch(console.error);
  }, [geojson, scores, stockout]);

  const maxScore = boroughs.length ? Math.max(...boroughs.map((b) => b.avg_score)) : 1;
  const minScore = boroughs.length ? Math.min(...boroughs.map((b) => b.avg_score)) : 0;

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold">Equity &amp; Access</h1>
          <p className="text-slate-400 text-sm mt-1">
            Transit accessibility by alcaldía — proximity score (Metro×3 + Metrobús×2 + EcoBici×1, normalized 0-100)
          </p>
        </div>

        {error && (
          <div className="bg-red-900/40 border border-red-700 text-red-300 rounded-xl px-5 py-4 text-sm">
            {error}
          </div>
        )}

        {/* Choropleth map */}
        <section>
          <h2 className="text-base font-semibold text-slate-300 mb-1">
            Accessibility score by alcaldía
          </h2>
          <p className="text-xs text-slate-500 mb-3">
            Red = low access · Green = high access. Computed from station proximity scores aggregated per borough.
          </p>
          <div className="rounded-xl overflow-hidden">
            {geojson && boroughs.length > 0 ? (
              <EquityMap geojson={geojson} boroughs={boroughs} height={480} minScore={minScore} maxScore={maxScore} />
            ) : (
              <div className="h-[480px] bg-slate-800 rounded-xl flex items-center justify-center text-slate-500 text-sm">
                {geojson ? "Computing borough scores…" : "Loading map…"}
              </div>
            )}
          </div>
        </section>

        {boroughs.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Accessibility score bar chart */}
            <section className="bg-slate-800 rounded-xl p-5">
              <h2 className="text-sm font-semibold text-slate-300 mb-3">
                Avg accessibility score by alcaldía
              </h2>
              <ResponsiveContainer width="100%" height={340}>
                <BarChart
                  data={boroughs}
                  layout="vertical"
                  margin={{ top: 4, right: 16, bottom: 0, left: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
                  <XAxis
                    type="number"
                    domain={[0, maxScore]}
                    tick={{ fontSize: 10, fill: "#94a3b8" }}
                    tickFormatter={(v: number) => v.toFixed(1)}
                  />
                  <YAxis
                    type="category"
                    dataKey="borough"
                    tick={{ fontSize: 10, fill: "#94a3b8" }}
                    width={110}
                  />
                  <Tooltip
                    contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                    itemStyle={{ fontSize: 11 }}
                    formatter={(v: number) => v.toFixed(1)}
                  />
                  <Bar dataKey="avg_score" name="Score" radius={[0, 3, 3, 0]}>
                    {boroughs.map((b) => (
                      <Cell key={b.borough} fill={scoreGradient(b.avg_score, minScore, maxScore)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </section>

            {/* Stockout bar chart */}
            <section className="bg-slate-800 rounded-xl p-5">
              <h2 className="text-sm font-semibold text-slate-300 mb-3">
                Avg EcoBici stockout by alcaldía (30 days)
              </h2>
              <ResponsiveContainer width="100%" height={340}>
                <BarChart
                  data={[...boroughs].sort(
                    (a, b) => b.avg_stockout_minutes - a.avg_stockout_minutes
                  )}
                  layout="vertical"
                  margin={{ top: 4, right: 16, bottom: 0, left: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fontSize: 10, fill: "#94a3b8" }}
                    tickFormatter={(v: number) => `${v}m`}
                  />
                  <YAxis
                    type="category"
                    dataKey="borough"
                    tick={{ fontSize: 10, fill: "#94a3b8" }}
                    width={110}
                  />
                  <Tooltip
                    contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                    itemStyle={{ fontSize: 11 }}
                    formatter={(v: number) => [`${v.toFixed(0)} min`, "Avg stockout"]}
                  />
                  <Bar
                    dataKey="avg_stockout_minutes"
                    name="Avg stockout (min)"
                    fill="#ef4444"
                    fillOpacity={0.75}
                    radius={[0, 3, 3, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
