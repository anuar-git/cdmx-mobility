"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ErrorBar,
} from "recharts";
import { api } from "@/lib/api";
import type {
  StationRow,
  HourlyRow,
  WeatherScatterRow,
  NeighborRow,
  ForecastRow,
} from "@/lib/types";
import { MODE_COLORS } from "@/lib/colors";

const NeighborsMap = dynamic(() => import("@/components/NeighborsMap"), {
  ssr: false,
  loading: () => (
    <div className="h-[340px] bg-slate-800 rounded-xl flex items-center justify-center text-slate-500 text-sm">
      Loading map…
    </div>
  ),
});

export default function StationPage() {
  const [stations, setStations] = useState<StationRow[]>([]);
  const [selected, setSelected] = useState<StationRow | null>(null);
  const [hourly, setHourly] = useState<HourlyRow[]>([]);
  const [scatter, setScatter] = useState<WeatherScatterRow[]>([]);
  const [neighbors, setNeighbors] = useState<NeighborRow[]>([]);
  const [forecast, setForecast] = useState<ForecastRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load EcoBici station list on mount
  useEffect(() => {
    api
      .stationList()
      .then((rows) =>
        setStations(rows.filter((r) => r.mode === "ecobici"))
      )
      .catch((e: Error) => setError(e.message));
  }, []);

  // Fetch all station data when selection changes
  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    setError(null);
    Promise.all([
      api.stationHourly(selected.station_id, 30),
      api.stationWeatherScatter(selected.station_id),
      api.stationNeighbors(selected.station_id),
      api.stationForecast(selected.station_id),
    ])
      .then(([h, w, n, f]) => {
        setHourly(h);
        setScatter(w);
        setNeighbors(n);
        setForecast(f);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selected]);

  const handleSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const s = stations.find((st) => st.station_id === e.target.value) ?? null;
    setSelected(s);
  };

  // Aggregate hourly to last 30 days by hour_ts for the area chart (deduplicated)
  const hourlyChart = hourly.slice(-24 * 7);

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
        {/* Header + picker */}
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <h1 className="text-2xl font-bold">Station Deep-Dive</h1>
            <p className="text-slate-400 text-sm mt-1">
              Hourly demand, weather sensitivity, neighbors, 24h forecast
            </p>
          </div>
          <div className="flex-1 min-w-[260px]">
            <label className="block text-xs text-slate-400 mb-1">EcoBici station</label>
            <select
              className="w-full bg-slate-800 border border-slate-600 text-slate-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              value={selected?.station_id ?? ""}
              onChange={handleSelect}
            >
              <option value="">— select a station —</option>
              {stations.map((s) => (
                <option key={s.station_id} value={s.station_id}>
                  {s.station_name}
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

        {loading && (
          <div className="text-slate-400 text-sm animate-pulse">Loading station data…</div>
        )}

        {selected && !loading && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Hourly demand — last 7 days */}
            <div className="bg-slate-800 rounded-xl p-5">
              <h2 className="text-sm font-semibold text-slate-300 mb-3">
                Hourly trips — last 7 days
              </h2>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart
                  data={hourlyChart}
                  margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis
                    dataKey="service_date"
                    tick={{ fontSize: 10, fill: "#94a3b8" }}
                    tickFormatter={(v: string) => v.slice(5)}
                    interval="preserveStartEnd"
                  />
                  <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} width={32} />
                  <Tooltip
                    contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                    labelStyle={{ color: "#cbd5e1", fontSize: 11 }}
                    itemStyle={{ color: "#4ade80", fontSize: 11 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="hourly_trips"
                    name="Trips"
                    stroke={MODE_COLORS.ecobici.hex}
                    fill={MODE_COLORS.ecobici.hex}
                    fillOpacity={0.3}
                    dot={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* 24-hour forecast */}
            <div className="bg-slate-800 rounded-xl p-5">
              <h2 className="text-sm font-semibold text-slate-300 mb-3">
                24-hour forecast (28-day same-hour avg)
              </h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart
                  data={forecast}
                  margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis
                    dataKey="hour_of_day"
                    tick={{ fontSize: 10, fill: "#94a3b8" }}
                    tickFormatter={(v: number) => `${v}h`}
                  />
                  <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} width={32} />
                  <Tooltip
                    contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                    labelStyle={{ color: "#cbd5e1", fontSize: 11 }}
                    itemStyle={{ color: "#4ade80", fontSize: 11 }}
                    labelFormatter={(v: number) => `Hour ${v}:00`}
                  />
                  <Bar
                    dataKey="forecast_trips"
                    name="Avg trips"
                    fill={MODE_COLORS.ecobici.hex}
                    fillOpacity={0.8}
                    radius={[3, 3, 0, 0]}
                  >
                    <ErrorBar dataKey="stddev_trips" width={3} strokeWidth={1.5} stroke="#86efac" />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Weather scatter */}
            <div className="bg-slate-800 rounded-xl p-5">
              <h2 className="text-sm font-semibold text-slate-300 mb-3">
                Temperature vs. daily trips
              </h2>
              <ResponsiveContainer width="100%" height={220}>
                <ScatterChart margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis
                    dataKey="avg_temperature_c"
                    name="Temp (°C)"
                    type="number"
                    tick={{ fontSize: 10, fill: "#94a3b8" }}
                    label={{ value: "°C", position: "insideRight", fill: "#64748b", fontSize: 10 }}
                  />
                  <YAxis
                    dataKey="daily_trips"
                    name="Trips"
                    tick={{ fontSize: 10, fill: "#94a3b8" }}
                    width={36}
                  />
                  <ZAxis range={[30, 30]} />
                  <Tooltip
                    contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                    itemStyle={{ color: "#cbd5e1", fontSize: 11 }}
                    cursor={{ strokeDasharray: "3 3" }}
                  />
                  <Scatter
                    data={scatter}
                    fill={MODE_COLORS.ecobici.hex}
                    fillOpacity={0.6}
                    name="Daily"
                  />
                  <Scatter
                    data={scatter.filter((d) => d.was_rainy)}
                    fill={MODE_COLORS.weather.hex}
                    fillOpacity={0.9}
                    name="Rainy day"
                  />
                </ScatterChart>
              </ResponsiveContainer>
            </div>

            {/* Neighbors map */}
            <div className="rounded-xl overflow-hidden">
              <h2 className="text-sm font-semibold text-slate-300 mb-3">
                Nearby stations (500 m radius)
              </h2>
              {neighbors.length > 0 ? (
                <NeighborsMap station={selected} neighbors={neighbors} height={340} />
              ) : (
                <div className="h-[340px] bg-slate-800 rounded-xl flex items-center justify-center text-slate-500 text-sm">
                  No neighbors found
                </div>
              )}
            </div>
          </div>
        )}

        {!selected && !loading && (
          <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
            Select a station above to explore its demand patterns.
          </div>
        )}
      </div>
    </div>
  );
}
