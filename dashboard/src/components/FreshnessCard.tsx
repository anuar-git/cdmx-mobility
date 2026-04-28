import type { FreshnessRow } from "@/lib/types";
import clsx from "clsx";

const SOURCE_LABELS: Record<string, string> = {
  ecobici: "EcoBici",
  metro: "Metro",
  metrobus: "Metrobús",
  weather: "Weather",
};

function formatLag(minutes: number | null): string {
  if (minutes === null) return "no data";
  if (minutes < 60) return `${Math.round(minutes)} min`;
  return `${(minutes / 60).toFixed(1)} hr`;
}

function formatTs(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-MX", {
    timeZone: "America/Mexico_City",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function FreshnessCard({ row }: { row: FreshnessRow }) {
  const violated = row.is_violated;
  const noData = row.lag_minutes === null;

  return (
    <div
      className={clsx(
        "rounded-xl border p-5 flex flex-col gap-3 shadow-sm",
        violated || noData
          ? "border-red-300 bg-red-50"
          : "border-green-300 bg-green-50"
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-600 uppercase tracking-wide">
          {SOURCE_LABELS[row.source] ?? row.source}
        </span>
        <span
          className={clsx(
            "text-xs font-bold px-2 py-1 rounded-full",
            violated || noData
              ? "bg-red-100 text-red-700"
              : "bg-green-100 text-green-700"
          )}
        >
          {noData ? "NO DATA" : violated ? "VIOLATED" : "OK"}
        </span>
      </div>

      <p className="text-3xl font-bold text-slate-900">
        {formatLag(row.lag_minutes)}
      </p>

      <div className="text-xs text-slate-500 space-y-1">
        <p>SLA: {row.sla_minutes} min</p>
        <p>Latest record: {formatTs(row.latest_ts)}</p>
      </div>
    </div>
  );
}
