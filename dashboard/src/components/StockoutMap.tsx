"use client";

import { ScatterplotLayer } from "@deck.gl/layers";
import DeckMap from "./DeckMap";
import type { StockoutRow } from "@/lib/types";

interface Props {
  data: StockoutRow[];
  height?: number;
}

function availabilityColor(ratio: number): [number, number, number, number] {
  // 0 (stockout) → red, 1 (full) → green
  const r = Math.round(220 * (1 - ratio));
  const g = Math.round(180 * ratio);
  return [r, g, 40, 200];
}

export default function StockoutMap({ data, height = 420 }: Props) {
  const layer = new ScatterplotLayer<StockoutRow>({
    id: "stockout",
    data,
    getPosition: (d) => [d.lon, d.lat],
    getRadius: (d) => Math.max(60, Math.sqrt(d.stockout_minutes + 1) * 70),
    getFillColor: (d) => availabilityColor(d.avg_availability_ratio ?? 0.5),
    radiusMinPixels: 5,
    radiusMaxPixels: 80,
    pickable: true,
    stroked: true,
    getLineColor: [255, 255, 255, 60],
    lineWidthMinPixels: 1,
  });

  return <DeckMap layers={[layer]} height={height} />;
}
