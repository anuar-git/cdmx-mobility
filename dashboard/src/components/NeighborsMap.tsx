"use client";

import { ScatterplotLayer } from "@deck.gl/layers";
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

export default function NeighborsMap({ station, neighbors, height = 340 }: Props) {
  const neighborsLayer = new ScatterplotLayer<NeighborRow>({
    id: "neighbors",
    data: neighbors,
    getPosition: (d) => [d.lon, d.lat],
    getRadius: 80,
    getFillColor: (d) => modeColor(d.mode),
    radiusMinPixels: 6,
    pickable: true,
  });

  const selectedLayer = new ScatterplotLayer<StationRow>({
    id: "selected",
    data: [station],
    getPosition: (d) => [d.lon, d.lat],
    getRadius: 120,
    getFillColor: [255, 220, 0, 255],
    radiusMinPixels: 10,
  });

  return (
    <DeckMap
      layers={[neighborsLayer, selectedLayer]}
      height={height}
      initialViewState={{ longitude: station.lon, latitude: station.lat, zoom: 14 }}
    />
  );
}
