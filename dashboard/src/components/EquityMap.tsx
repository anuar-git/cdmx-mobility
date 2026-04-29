"use client";

import { GeoJsonLayer } from "@deck.gl/layers";
import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
import { point } from "@turf/helpers";
import DeckMap from "./DeckMap";
import type { BoroughSummary } from "@/lib/types";

interface GeoFeature {
  type: "Feature";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  geometry: any;
  properties: { borough: string; [key: string]: unknown };
}

interface Props {
  geojson: { type: string; features: GeoFeature[] };
  boroughs: BoroughSummary[];
  height?: number;
}

type RGBA = [number, number, number, number];

function scoreColor(score: number): RGBA {
  const t = Math.max(0, Math.min(1, score / 100));
  return [
    Math.round(200 - t * 160),
    Math.round(40 + t * 160),
    Math.round(80 + t * 40),
    170,
  ];
}

export default function EquityMap({ geojson, boroughs, height = 480 }: Props) {
  const scoreMap = new Map(boroughs.map((b) => [b.borough, b.avg_score]));

  const enriched = {
    ...geojson,
    features: geojson.features.map((f) => ({
      ...f,
      properties: {
        ...f.properties,
        avg_score: scoreMap.get(f.properties.borough) ?? 0,
      },
    })),
  };

  const layer = new GeoJsonLayer({
    id: "equity-choropleth",
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    data: enriched as any,
    filled: true,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    getFillColor: (f: any) => scoreColor(f.properties?.avg_score ?? 0),
    stroked: true,
    getLineColor: [255, 255, 255, 120],
    lineWidthMinPixels: 1,
    pickable: true,
  });

  return <DeckMap layers={[layer]} height={height} />;
}

// Pure helper — exported so equity/page.tsx can call it without importing turf directly.
export function computeBoroughs(
  geojson: { features: GeoFeature[] },
  stations: { lat: number; lon: number; accessibility_score: number }[],
  stockoutMap: Map<string, number>
): BoroughSummary[] {
  const byBorough = new Map<
    string,
    { scoreSum: number; scoreCount: number; stockoutSum: number; stockoutCount: number }
  >();

  for (const s of stations) {
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
        byBorough.set(b, {
          scoreSum: cur.scoreSum + s.accessibility_score,
          scoreCount: cur.scoreCount + 1,
          stockoutSum: cur.stockoutSum + (stockoutMap.get(s.lat + "," + s.lon) ?? 0),
          stockoutCount: cur.stockoutCount + (stockoutMap.has(s.lat + "," + s.lon) ? 1 : 0),
        });
        break;
      }
    }
  }

  return Array.from(byBorough.entries())
    .map(([borough, agg]) => ({
      borough,
      avg_score: agg.scoreCount ? agg.scoreSum / agg.scoreCount : 0,
      station_count: agg.scoreCount,
      avg_stockout_minutes: agg.stockoutCount
        ? agg.stockoutSum / agg.stockoutCount
        : 0,
    }))
    .sort((a, b) => b.avg_score - a.avg_score);
}
