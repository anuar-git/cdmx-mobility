"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { api } from "@/lib/api";
import type { RidershipRow, StockoutRow, WeatherRow } from "@/lib/types";
import { MODE_COLORS } from "@/lib/colors";

const StockoutMap = dynamic(() => import("@/components/StockoutMap"), {
  ssr: false,
  loading: () => (
    <div className="h-[420px] bg-slate-800 rounded-xl flex items-center justify-center text-slate-500 text-sm">
      Loading map…
    </div>
  ),
});

function sortByDate(rows: RidershipRow[]): RidershipRow[] {
  return [...rows].sort((a, b) => (a.service_date < b.service_date ? -1 : 1));
}

function yFormatter(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

function WeatherBanner({ w }: { w: WeatherRow }) {
  return (
    <div className="bg-slate-800 rounded-xl px-5 py-4 flex flex-wrap items-center gap-6">
      <div>
        <p className="text-xs text-slate-400 uppercase tracking-wide">Condition</p>
        <p className="text-lg font-semibold text-white mt-0.5">{w.weather_condition}</p>
      </div>
      <div>
        <p className="text-xs text-slate-400 uppercase tracking-wide">Temperature</p>
        <p className="text-lg font-semibold text-white mt-0.5">{Math.round(w.temperature_c)}°C</p>
      </div>
      <div>
        <p className="text-xs text-slate-400 uppercase tracking-wide">Humidity</p>
        <p className="text-lg font-semibold text-white mt-0.5">{w.humidity_pct}%</p>
      </div>
      <div>
        <p className="text-xs text-slate-400 uppercase tracking-wide">Precip.</p>
        <p className="text-lg font-semibold text-white mt-0.5">{w.precipitation_mm} mm</p>
      </div>
      <div>
        <p className="text-xs text-slate-400 uppercase tracking-wide">Comfort</p>
        <p className="text-lg font-semibold text-white mt-0.5">{Math.round(w.comfort_score)}/100</p>
      </div>
      {w.is_adverse_weather && (
        <span className="ml-auto px-3 py-1 bg-red-800 text-red-200 text-xs font-bold rounded-full">
          ADVERSE
        </span>
      )}
    </div>
  );
}

export default function PulsePage() {
  const [ridership, setRidership] = useState<RidershipRow[]>([]);
  const [stockout, setStockout] = useState<StockoutRow[]>([]);
  const [weather, setWeather] = useState<WeatherRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.pulseRidership(60),
      api.pulseStockout(20),
      api.pulseWeather(),
    ])
      .then(([r, s, w]) => {
        setRidership(r);
        setStockout(s);
        setWeather(w);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const metroData    = sortByDate(ridership.filter((r) => r.mode === "metro"));
  const metrobusData = sortByDate(ridership.filter((r) => r.mode === "metrobus")).slice(-8);
  const ecobiciData  = sortByDate(ridership.filter((r) => r.mode === "ecobici")).slice(-8);

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold">City Pulse</h1>
          <p className="text-slate-400 text-sm mt-1">
            Live operational snapshot — ridership, EcoBici stress, weather
          </p>
        </div>

        {error && (
          <div className="bg-red-900/40 border border-red-700 text-red-300 rounded-xl px-5 py-4 text-sm">
            {error}
          </div>
        )}

        {/* Weather banner */}
        {weather && weather.temperature_c != null && <WeatherBanner w={weather} />}

        {/* Ridership charts — one per mode */}
        <section>
          <h2 className="text-base font-semibold text-slate-300 mb-3">
            Daily ridership
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {(
              [
                { label: "Metro",     data: metroData,    color: MODE_COLORS.metro.hex },
                { label: "Metrobús",  data: metrobusData, color: MODE_COLORS.metrobus.hex },
                { label: "EcoBici",   data: ecobiciData,  color: MODE_COLORS.ecobici.hex },
              ] as const
            ).map(({ label, data, color }) => (
              <div key={label} className="bg-slate-800 rounded-xl p-4">
                <p className="text-xs font-semibold mb-2" style={{ color }}>{label}</p>
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis
                      dataKey="service_date"
                      tick={{ fontSize: 10, fill: "#94a3b8" }}
                      tickFormatter={(v: string) => v.slice(5)}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: "#94a3b8" }}
                      tickFormatter={yFormatter}
                      width={48}
                    />
                    <Tooltip
                      contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                      labelStyle={{ color: "#cbd5e1", fontSize: 11 }}
                      itemStyle={{ color: "#cbd5e1", fontSize: 11 }}
                      formatter={(v: number) => [v.toLocaleString(), label]}
                    />
                    <Line
                      type="monotone"
                      dataKey="ridership"
                      stroke={color}
                      dot={false}
                      strokeWidth={2}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ))}
          </div>
        </section>

        {/* Stockout map */}
        <section>
          <h2 className="text-base font-semibold text-slate-300 mb-1">
            EcoBici station stress — top 20 by stockout today
          </h2>
          <p className="text-xs text-slate-500 mb-3">
            Circle size = stockout minutes · Red = low availability · Green = high availability
          </p>
          <div className="rounded-xl overflow-hidden">
            <StockoutMap data={stockout} height={420} />
          </div>
        </section>

        {/* Top-N table */}
        {stockout.length > 0 && (
          <section>
            <h2 className="text-base font-semibold text-slate-300 mb-3">
              Stockout detail
            </h2>
            <div className="bg-slate-800 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 text-xs text-slate-400 uppercase tracking-wide">
                    <th className="text-left px-4 py-3">Station</th>
                    <th className="text-right px-4 py-3">Stockout min</th>
                    <th className="text-right px-4 py-3">Trips today</th>
                    <th className="text-right px-4 py-3">Availability</th>
                  </tr>
                </thead>
                <tbody>
                  {stockout.slice(0, 10).map((s) => (
                    <tr
                      key={s.station_id}
                      className="border-b border-slate-700/50 hover:bg-slate-700/30"
                    >
                      <td className="px-4 py-2.5 text-slate-200">{s.station_name}</td>
                      <td className="px-4 py-2.5 text-right text-red-400 font-mono">
                        {Math.round(s.stockout_minutes)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-slate-300">
                        {s.daily_trips.toLocaleString()}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-slate-300">
                        {(s.avg_availability_ratio * 100).toFixed(0)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
