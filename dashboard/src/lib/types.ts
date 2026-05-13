// ─── Pipeline health (existing) ───────────────────────────────────────────────
export interface PipelineHealthRow {
  run_date: string;
  canonical_source: "ecobici" | "metro" | "metrobus" | "weather";
  total_rows_ingested: number;
  ingest_success_runs: number;
  ingest_error_runs: number;
  ingest_skipped_runs: number;
  dbt_total_runtime_seconds: number | null;
  dbt_test_pass_rate_pct: number | null;
  gx_pass_rate_pct: number | null;
  gx_all_suites_passed: boolean | null;
  freshness_lag_minutes: number | null;
  freshness_sla_minutes: number | null;
  freshness_sla_violated: boolean | null;
}

export interface FreshnessRow {
  source: string;
  latest_ts: string | null;
  lag_minutes: number | null;
  sla_minutes: number;
  is_violated: boolean;
  checked_at: string;
}

export interface TestsRow {
  run_date: string;
  dbt_tests_passed: number;
  dbt_tests_failed: number;
  dbt_tests_total: number;
  dbt_test_pass_rate_pct: number | null;
}

export interface RuntimeRow {
  run_date: string;
  dbt_total_runtime_seconds: number | null;
  dbt_models_succeeded: number;
  dbt_models_failed: number;
}

export interface IngestionRow {
  run_date: string;
  canonical_source: string;
  total_rows_ingested: number;
  total_bytes: number;
  total_files: number;
  ingest_success_runs: number;
  ingest_error_runs: number;
}

// ─── Pulse ────────────────────────────────────────────────────────────────────
export interface RidershipRow {
  service_date: string;
  mode: "metro" | "metrobus" | "ecobici";
  ridership: number;
}

export interface StockoutRow {
  station_id: string;
  station_name: string;
  lat: number;
  lon: number;
  stockout_minutes: number;
  full_minutes: number;
  daily_trips: number;
  avg_availability_ratio: number;
  capacity: number;
}

export interface WeatherRow {
  hour_ts: string;
  service_date: string;
  temperature_c: number;
  humidity_pct: number;
  precipitation_mm: number;
  windspeed_ms: number;
  comfort_score: number;
  weather_condition: string;
  is_rainy: boolean;
  is_adverse_weather: boolean;
}

// ─── Station deep-dive ────────────────────────────────────────────────────────
export interface StationRow {
  station_id: string;
  station_key: string;
  station_name: string;
  mode: "ecobici" | "metro" | "metrobus";
  lat: number;
  lon: number;
  capacity: number | null;
  linea: string | null;
  borough: string | null;
}

export interface HourlyRow {
  hour_ts: string;
  service_date: string;
  hourly_trips: number;
  bikes_available_avg: number;
  docks_available_avg: number;
  stockout_minutes: number;
  availability_ratio: number;
}

export interface WeatherScatterRow {
  service_date: string;
  daily_trips: number;
  avg_temperature_c: number;
  avg_humidity_pct: number;
  avg_precipitation_mm: number;
  was_rainy: boolean;
  was_adverse_weather: boolean;
}

export interface NeighborRow {
  station_id: string;
  station_name: string;
  mode: string;
  lat: number;
  lon: number;
  distance_m: number;
  bikes_available_avg: number | null;
  availability_ratio: number | null;
}

export interface ForecastRow {
  hour_of_day: number;
  forecast_trips: number;
  stddev_trips: number | null;
  sample_hours: number;
}

// ─── Modal substitution ───────────────────────────────────────────────────────
export interface ModalLineRow {
  metro_line: string;
  days_with_data: number;
  avg_daily_ridership: number;
  avg_nearby_metrobus_events: number;
  avg_nearby_ecobici_trips: number;
  low_service_days: number;
}

export interface SubstitutionRow {
  service_date: string;
  metro_daily_entries: number;
  metro_7d_avg: number;
  metro_vs_avg_ratio: number;
  is_low_service_day: boolean;
  nearby_metrobus_events: number;
  nearby_metrobus_vehicles: number;
  nearby_ecobici_trips: number;
  nearby_ecobici_availability: number | null;
}

export interface CorridorRow {
  station_id: string;
  station_name: string;
  mode: string;
  lat: number;
  lon: number;
  line_label: string | null;
  distance_m: number | null;
  metro_daily_entries: number | null;
  metro_latest_date: string | null;
  ecobici_bikes_available: number | null;
  ecobici_availability_pct: number | null;
  metrobus_avg_headway_min: number | null;
  metrobus_routes: string | null;
}

// ─── Equity & access ──────────────────────────────────────────────────────────
export interface AccessibilityRow {
  station_id: string;
  station_name: string;
  mode: string;
  lat: number;
  lon: number;
  accessibility_score: number;
  nearby_mode_count: number;
  nearby_metro_count: number;
  nearby_metrobus_count: number;
  nearby_ecobici_count: number;
}

export interface StockoutByBoroughRow {
  station_id: string;
  station_name: string;
  lat: number;
  lon: number;
  avg_stockout_minutes: number;
  avg_full_minutes: number;
  avg_availability_ratio: number;
  days_with_data: number;
}

export interface BoroughSummary {
  borough: string;
  avg_score: number;
  station_count: number;
  avg_stockout_minutes: number;
}
