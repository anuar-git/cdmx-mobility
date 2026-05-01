"use client";

import DeckGL from "@deck.gl/react";
import type { PickingInfo } from "@deck.gl/core";
import { Map } from "react-map-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { CDMX_VIEW_STATE, MAPBOX_STYLE } from "@/lib/colors";

export interface ViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  pitch?: number;
  bearing?: number;
}

interface Props {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  layers: any[];
  height?: number;
  initialViewState?: ViewState;
  getCursor?: (state: { isDragging: boolean; isHovering: boolean }) => string;
  getTooltip?: (info: PickingInfo) => { html: string; style?: object } | null;
}

export default function DeckMap({
  layers,
  height = 420,
  initialViewState = CDMX_VIEW_STATE,
  getCursor,
  getTooltip,
}: Props) {
  return (
    <div style={{ height, position: "relative" }}>
      <DeckGL
        initialViewState={initialViewState}
        controller={true}
        layers={layers}
        {...(getCursor ? { getCursor } : {})}
        {...(getTooltip ? { getTooltip } : {})}
      >
        <Map
          mapboxAccessToken={process.env.NEXT_PUBLIC_MAPBOX_TOKEN}
          mapStyle={MAPBOX_STYLE}
        />
      </DeckGL>
    </div>
  );
}
