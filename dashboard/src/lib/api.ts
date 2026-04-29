import type {
  FreshnessRow,
  IngestionRow,
  PipelineHealthRow,
  RuntimeRow,
  TestsRow,
  RidershipRow,
  StockoutRow,
  WeatherRow,
  StationRow,
  HourlyRow,
  WeatherScatterRow,
  NeighborRow,
  ForecastRow,
  ModalLineRow,
  SubstitutionRow,
  CorridorRow,
  AccessibilityRow,
  StockoutByBoroughRow,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    next: { revalidate: 300 },
  });
  if (!res.ok) throw new Error(`API ${path} returned ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  // Pipeline health (existing)
  health: (days = 30) =>
    get<PipelineHealthRow[]>(`/api/pipeline/health?days=${days}`),
  freshness: () => get<FreshnessRow[]>("/api/pipeline/freshness"),
  tests: (days = 30) => get<TestsRow[]>(`/api/pipeline/tests?days=${days}`),
  runtime: (days = 30) =>
    get<RuntimeRow[]>(`/api/pipeline/runtime?days=${days}`),
  ingestion: (days = 30) =>
    get<IngestionRow[]>(`/api/pipeline/ingestion?days=${days}`),

  // Pulse
  pulseRidership: (days = 8) =>
    get<RidershipRow[]>(`/api/pulse/ridership?days=${days}`),
  pulseStockout: (limit = 20) =>
    get<StockoutRow[]>(`/api/pulse/stockout?limit=${limit}`),
  pulseWeather: () => get<WeatherRow>("/api/pulse/weather"),

  // Station
  stationList: () => get<StationRow[]>("/api/station/list"),
  stationHourly: (id: string, days = 30) =>
    get<HourlyRow[]>(`/api/station/${id}/hourly?days=${days}`),
  stationWeatherScatter: (id: string) =>
    get<WeatherScatterRow[]>(`/api/station/${id}/weather-scatter`),
  stationNeighbors: (id: string, radiusM = 500) =>
    get<NeighborRow[]>(`/api/station/${id}/neighbors?radius_m=${radiusM}`),
  stationForecast: (id: string) =>
    get<ForecastRow[]>(`/api/station/${id}/forecast`),

  // Modal substitution
  modalLines: () => get<ModalLineRow[]>("/api/modal/lines"),
  modalSubstitution: (line: string, days = 90) =>
    get<SubstitutionRow[]>(
      `/api/modal/substitution?line=${encodeURIComponent(line)}&days=${days}`
    ),
  modalCorridor: (line: string) =>
    get<CorridorRow[]>(
      `/api/modal/corridor?line=${encodeURIComponent(line)}`
    ),

  // Equity
  equityScores: () => get<AccessibilityRow[]>("/api/equity/scores"),
  equityStockoutByBorough: (days = 30) =>
    get<StockoutByBoroughRow[]>(
      `/api/equity/stockout-by-borough?days=${days}`
    ),
};
