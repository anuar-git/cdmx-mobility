"use client";

import { ScatterplotLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import DeckMap from "./DeckMap";
import type { NeighborRow, StationRow } from "@/lib/types";
import { MODE_COLORS } from "@/lib/colors";

interface Props {
  station: StationRow;
  neighbors: NeighborRow[];
  height?: number;
}

type RGBA = [number, number, number, number];

function modeColor(mode: string): RGBA {
  const c = MODE_COLORS[mode as keyof typeof MODE_COLORS];
  return c ? ([...c.rgb, 220] as RGBA) : [150, 150, 150, 200];
}

function tooltip(info: PickingInfo<NeighborRow | StationRow>) {
  if (!info.object) return null;
  const obj = info.object;

  if ("distance_m" in obj) {
    // NeighborRow
    const n = obj as NeighborRow;
    let availability = "";
    if (n.mode === "ecobici") {
      availability =
        n.bikes_available_avg != null
          ? `<div style="margin-top:4px;color:#4ade80">🚲 ${Math.round(n.bikes_available_avg)} bikes · ${Math.round((n.availability_ratio ?? 0) * 100)}% available</div>`
          : `<div style="margin-top:4px;color:#64748b">No recent availability data</div>`;
    }
    return {
      html: `<div style="font-weight:600">${n.station_name}</div>
             <div style="color:#94a3b8;font-size:11px;margin-top:2px">${n.mode} · ${Math.round(n.distance_m)} m away</div>
             ${availability}`,
      style: { background: "#1e293b", color: "#e2e8f0", padding: "8px 10px", borderRadius: "6px", fontSize: "12px", maxWidth: "220px" },
    };
  }

  // StationRow (the selected station)
  const s = obj as StationRow;
  return {
    html: `<div style="font-weight:600">${s.station_name}</div>
           <div style="color:#fde047;font-size:11px;margin-top:2px">Selected station</div>`,
    style: { background: "#1e293b", color: "#e2e8f0", padding: "8px 10px", borderRadius: "6px", fontSize: "12px" },
  };
}

const LEGEND = [
  { label: "EcoBici",   color: MODE_COLORS.ecobici.hex },
  { label: "Metrobús",  color: MODE_COLORS.metrobus.hex },
  { label: "Metro",     color: MODE_COLORS.metro.hex },
];

export default function NeighborsMap({ station, neighbors, height = 340 }: Props) {
  const neighborsLayer = new ScatterplotLayer<NeighborRow>({
    id: "neighbors",
    data: neighbors,
    getPosition: (d) => [d.lon, d.lat],
    getRadius: 35,
    getFillColor: (d) => modeColor(d.mode),
    radiusMinPixels: 4,
    radiusMaxPixels: 10,
    pickable: true,
  });

  const selectedLayer = new ScatterplotLayer<StationRow>({
    id: "selected",
    data: [station],
    getPosition: (d) => [d.lon, d.lat],
    getRadius: 50,
    getFillColor: [255, 220, 0, 255],
    radiusMinPixels: 6,
    radiusMaxPixels: 14,
    pickable: true,
  });

  return (
    <div style={{ position: "relative", height }}>
      <DeckMap
        layers={[neighborsLayer, selectedLayer]}
        height={height}
        initialViewState={{ longitude: station.lon, latitude: station.lat, zoom: 14 }}
        getTooltip={tooltip}
        getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}
      />
      <div style={{
        position: "absolute", bottom: 8, right: 8,
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
