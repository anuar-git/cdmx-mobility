"use client";

import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import DeckMap from "./DeckMap";
import type { CorridorRow } from "@/lib/types";
import { MODE_COLORS } from "@/lib/colors";

interface Props {
  data: CorridorRow[];
  height?: number;
}

type RGBA = [number, number, number, number];

function modeColor(mode: string): RGBA {
  const c = MODE_COLORS[mode as keyof typeof MODE_COLORS];
  return c ? ([...c.rgb, 220] as RGBA) : [150, 150, 150, 200];
}

interface ArcDatum {
  source: [number, number];
  target: [number, number];
  targetMode: string;
}

function tooltip(info: PickingInfo<CorridorRow>) {
  if (!info.object) return null;
  const d = info.object;

  let body = "";

  if (d.mode === "metro") {
    const entries =
      d.metro_daily_entries != null
        ? `<div style="margin-top:4px;color:#fb923c">🚇 ${d.metro_daily_entries.toLocaleString()} entries · ${d.metro_latest_date ?? ""}</div>`
        : `<div style="margin-top:4px;color:#64748b">No recent ridership data</div>`;
    body = `<div style="color:#94a3b8;font-size:11px;margin-top:2px">Metro · ${d.line_label ?? ""}</div>${entries}`;
  } else if (d.mode === "ecobici") {
    body =
      d.ecobici_bikes_available != null
        ? `<div style="color:#94a3b8;font-size:11px;margin-top:2px">EcoBici · ${Math.round(d.distance_m ?? 0)} m away</div>` +
          `<div style="margin-top:4px;color:#4ade80">🚲 ${d.ecobici_bikes_available} bikes · ${d.ecobici_availability_pct ?? 0}% available</div>`
        : `<div style="color:#94a3b8;font-size:11px;margin-top:2px">EcoBici · ${Math.round(d.distance_m ?? 0)} m away</div>` +
          `<div style="margin-top:4px;color:#64748b">No live availability data</div>`;
  } else {
    // metrobus
    const headway =
      d.metrobus_avg_headway_min != null
        ? `<div style="margin-top:4px;color:#f87171">🚌 Avg headway: ${d.metrobus_avg_headway_min} min</div>`
        : "";
    const routes = d.metrobus_routes
      ? `<div style="margin-top:2px;color:#94a3b8;font-size:11px">Routes: ${d.metrobus_routes}</div>`
      : "";
    body =
      `<div style="color:#94a3b8;font-size:11px;margin-top:2px">Metrobús · ${Math.round(d.distance_m ?? 0)} m away</div>` +
      headway +
      routes;
  }

  return {
    html: `<div style="font-weight:600">${d.station_name}</div>${body}`,
    style: {
      background: "#1e293b",
      color: "#e2e8f0",
      padding: "8px 10px",
      borderRadius: "6px",
      fontSize: "12px",
      maxWidth: "240px",
    },
  };
}

const LEGEND = [
  { label: "Metro",     color: MODE_COLORS.metro.hex },
  { label: "Metrobús",  color: MODE_COLORS.metrobus.hex },
  { label: "EcoBici",   color: MODE_COLORS.ecobici.hex },
];

export default function CorridorMap({ data, height = 420 }: Props) {
  const metroStops = data.filter((d) => d.mode === "metro");
  const altStops = data.filter((d) => d.mode !== "metro");

  const arcs: ArcDatum[] = altStops
    .map((alt) => {
      if (!metroStops.length) return null;
      const nearest = metroStops.reduce(
        (best, m) => {
          const dist = Math.hypot(m.lat - alt.lat, m.lon - alt.lon);
          return dist < best.dist ? { stop: m, dist } : best;
        },
        { stop: metroStops[0], dist: Infinity }
      );
      return {
        source: [nearest.stop.lon, nearest.stop.lat] as [number, number],
        target: [alt.lon, alt.lat] as [number, number],
        targetMode: alt.mode,
      };
    })
    .filter((d): d is ArcDatum => d !== null);

  const stationsLayer = new ScatterplotLayer<CorridorRow>({
    id: "corridor-stations",
    data,
    getPosition: (d) => [d.lon, d.lat],
    getRadius: 60,
    getFillColor: (d) => modeColor(d.mode),
    radiusMinPixels: 5,
    pickable: true,
  });

  const arcsLayer = new ArcLayer<ArcDatum>({
    id: "corridor-arcs",
    data: arcs,
    getSourcePosition: (d) => d.source,
    getTargetPosition: (d) => d.target,
    getSourceColor: [...MODE_COLORS.metro.rgb, 160] as RGBA,
    getTargetColor: (d) => modeColor(d.targetMode),
    getWidth: 2,
    widthMinPixels: 1,
  });

  return (
    <div style={{ position: "relative", height }}>
      <DeckMap
        layers={[arcsLayer, stationsLayer]}
        height={height}
        getTooltip={tooltip}
        getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}
      />
      <div style={{
        position: "absolute", bottom: 8, left: 8,
        background: "rgba(15,23,42,0.85)", borderRadius: 6,
        padding: "6px 10px", display: "flex", flexDirection: "column", gap: 4,
      }}>
        {LEGEND.map(({ label, color }) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 10, height: 10, borderRadius: "50%", background: color, flexShrink: 0 }} />
            <span style={{ fontSize: 11, color: "#cbd5e1" }}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
