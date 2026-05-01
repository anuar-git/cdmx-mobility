"use client";

import { ScatterplotLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import DeckMap from "./DeckMap";
import type { StationRow } from "@/lib/types";
import { MODE_COLORS } from "@/lib/colors";

interface Props {
  stations: StationRow[];
  selected: StationRow | null;
  onSelect: (s: StationRow) => void;
  height?: number;
}

export default function StationPickerMap({
  stations,
  selected,
  onSelect,
  height = 380,
}: Props) {
  const allLayer = new ScatterplotLayer<StationRow>({
    id: "all-stations",
    data: stations,
    getPosition: (d) => [d.lon, d.lat],
    getRadius: 60,
    getFillColor: [...MODE_COLORS.ecobici.rgb, 180],
    radiusMinPixels: 5,
    radiusMaxPixels: 14,
    pickable: true,
    stroked: true,
    getLineColor: [255, 255, 255, 40],
    lineWidthMinPixels: 1,
    onClick: (info: PickingInfo<StationRow>) => {
      if (info.object) onSelect(info.object);
    },
  });

  const selectedLayer = new ScatterplotLayer<StationRow>({
    id: "selected-station",
    data: selected ? [selected] : [],
    getPosition: (d) => [d.lon, d.lat],
    getRadius: 120,
    getFillColor: [255, 220, 0, 255],
    stroked: true,
    getLineColor: [255, 255, 255, 200],
    lineWidthMinPixels: 2,
    radiusMinPixels: 10,
    radiusMaxPixels: 20,
  });

  return (
    <DeckMap
      layers={[allLayer, selectedLayer]}
      height={height}
      getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}
    />
  );
}
