// Brand colors for each transport mode, matching official CDMX transit identity.
// hex: CSS string. rgb: Deck.gl getFillColor / getColor array [R, G, B].
export const MODE_COLORS = {
  metro: {
    hex: "#E37221",
    rgb: [227, 114, 33] as [number, number, number],
  },
  metrobus: {
    hex: "#CC0000",
    rgb: [204, 0, 0] as [number, number, number],
  },
  ecobici: {
    hex: "#00A651",
    rgb: [0, 166, 81] as [number, number, number],
  },
  weather: {
    hex: "#64B5F6",
    rgb: [100, 181, 246] as [number, number, number],
  },
} as const;

export type TransportMode = keyof typeof MODE_COLORS;

// Sequential scale for choropleth (low → high accessibility).
// 5 quantile stops from light yellow to dark green.
export const ACCESSIBILITY_SCALE = [
  "#ffffb2",
  "#fecc5c",
  "#fd8d3c",
  "#f03b20",
  "#bd0026",
] as const;

// Deck.gl map style — dark basemap maximises contrast with transit layers.
export const MAPBOX_STYLE = "mapbox://styles/mapbox/dark-v11";

// Default view centred on CDMX historic core.
export const CDMX_VIEW_STATE = {
  longitude: -99.133,
  latitude: 19.432,
  zoom: 11,
  pitch: 0,
  bearing: 0,
} as const;
