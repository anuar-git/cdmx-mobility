"use client";

import DeckGL from "@deck.gl/react";
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
}

export default function DeckMap({
  layers,
  height = 420,
  initialViewState = CDMX_VIEW_STATE,
}: Props) {
  return (
    <div style={{ height, position: "relative" }}>
      <DeckGL
        initialViewState={initialViewState}
        controller={true}
        layers={layers}
      >
        <Map
          mapboxAccessToken={process.env.NEXT_PUBLIC_MAPBOX_TOKEN}
          mapStyle={MAPBOX_STYLE}
        />
      </DeckGL>
    </div>
  );
}
