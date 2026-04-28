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
