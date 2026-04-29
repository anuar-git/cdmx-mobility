"use client";

import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
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

  return <DeckMap layers={[arcsLayer, stationsLayer]} height={height} />;
}
