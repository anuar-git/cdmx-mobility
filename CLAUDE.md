# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`cdmx-mobility` is a GCP-based data engineering platform for Mexico City mobility data. It follows a medallion architecture: raw ingestion → dbt models in BigQuery → Tableau dashboards.

GCP project ID: `cdmx-mobility-prod`.
GCS raw bucket: `cdmx-mobility-data`.

## Package Management

This project uses **uv** (not pip or poetry). Install dependencies with:

```bash
uv sync
```

The `.envrc` auto-activates the venv via direnv. Python version is pinned to 3.11.9 in `.python-version`.

Prefix all Python tool invocations with `uv run` (e.g. `uv run pytest`, `uv run dbt build`).

## Common Commands

```bash
# Linting & formatting
uv run ruff check .
uv run black .

# Type checking
uv run mypy .

# SQL linting (dbt models) — config in .sqlfluff
uv run sqlfluff lint dbt_bigquery/models --dialect bigquery

# Tests
uv run pytest
uv run pytest tests/path/test_file.py::TestClass::test_method -v   # single test
uv run pytest tests/ --cov=ingestion --cov=spark_jobs              # with coverage

# Pre-commit (runs all checks)
pre-commit run --all-files

# Run ingestors locally (one-shot)
CDMX_GCP_PROJECT_ID=cdmx-mobility-prod uv run python main.py ingest-metro-affluence
CDMX_GCP_PROJECT_ID=cdmx-mobility-prod uv run python main.py ingest-ecobici-gbfs
CDMX_GCP_PROJECT_ID=cdmx-mobility-prod uv run python main.py ingest-metrobus-gtfs-static

# Run the GTFS-RT daemon locally (long-running, Ctrl-C to stop)
CDMX_GCP_PROJECT_ID=cdmx-mobility-prod \
CDMX_METROBUS_GTFS_RT_VEHICLE_POSITIONS_URL=https://... \
  uv run python main.py run-metrobus-gtfs-rt-daemon

# dbt (run from dbt_bigquery/)
cd dbt_bigquery/
uv run dbt build
uv run dbt run --select stg_metro_affluence
uv run dbt run --select stg_ecobici_station_status stg_ecobici_station_information
uv run dbt run --select mart_ecobici_availability_2min
uv run dbt run --select stg_metrobus_stops stg_metrobus_routes stg_metrobus_vehicle_positions
uv run dbt run --select mart_metrobus_vehicle_positions_hourly
uv run dbt test
```

## Architecture

```
datos.cdmx.gob.mx (CKAN)                                    SEMOVI GTFS-RT endpoint
  │  afluencia-diaria-del-metro-cdmx                           │  (URL via Secret/env var)
  │  gtfs (unified CDMX static ZIP — Metro, Metrobús, …)       │
  │                                                            │
  ├─────────────────────┬─────────────────────┐               │
  ▼                     ▼                     ▼               ▼
ingestion/metro/   ingestion/metrobus/   ingestion/metrobus/  ingestion/ecobici/
 affluence.py       gtfs_static.py        gtfs_rt.py           gbfs.py
 CKANClient         CKANClient            httpx + protobuf     GBFSClient
 (CI, daily)        (Cloud Run Job,        (Cloud Run Service,  (Cloud Run Job,
                     daily 04:00)           always-on daemon)   every 2 min)
  │                     │                     │               │
  ▼                     ▼                     ▼               ▼
gs://cdmx-mobility-data/
  metro/affluence/ingestion_date=YYYY-MM-DD/
  metrobus/static/{feed}/ingestion_date=YYYY-MM-DD/     ← stops, routes, trips, stop_times, calendar, shapes
  metrobus/vehicle_positions/ingestion_date=YYYY-MM-DD/ ← ~2,880 .ndjson/day (BigQuery)
  metrobus/vehicle_positions_raw/ingestion_date=YYYY-MM-DD/ ← ~2,880 .pb/day (archival)
  ecobici/station_status/ingestion_ts=YYYY-MM-DDTHH-MM/
  ecobici/station_information/ingestion_date=YYYY-MM-DD/
  ecobici/system_alerts/ingestion_ts=YYYY-MM-DDTHH-MM/
  │
  ▼  (BigQuery external tables in raw_cdmx)
dbt_bigquery/models/staging/
  stg_metro_affluence.sql
  stg_ecobici_station_{status,information}.sql
  stg_metrobus_{stops,routes,vehicle_positions}.sql
  │
  ▼
dbt_bigquery/models/marts/
  mart_metro_affluence_daily.sql
  mart_ecobici_availability_2min.sql
  mart_metrobus_vehicle_positions_hourly.sql   ← partitioned by hour, clustered on route_id
  │
  ▼
Tableau (reads from marts_cdmx)
```

**Modules:**
- [ingestion/](ingestion/) — HTTP ingestors. Config via Pydantic settings (`ingestion/config.py`, `CDMX_` env prefix). Primitives: `CKANClient`, `GBFSClient`, `GCSUploader`, `IngestionLogger` / `RunResult` (BQ metadata), `validate_csv_header` / `validate_gbfs_envelope` (schema validation).
- [ingestion/metro/](ingestion/metro/) — Metro affluence ingestor. One-shot batch, runs in CI on every push to main. CKAN dataset: `afluencia-diaria-del-metro-cdmx`; data columns: `fecha, anio, mes, linea, estacion, afluencia`. Dictionary resources are filtered before upload.
- [ingestion/ecobici/](ingestion/ecobici/) — EcoBici GBFS ingestor (`station_status`, `station_information`, `system_alerts`). Cloud Run Job every 2 minutes.
- [ingestion/metrobus/](ingestion/metrobus/) — Two ingestors:
  - `gtfs_static.py` — Downloads the SEMOVI unified CDMX GTFS ZIP via CKAN, unpacks the 6 standard feeds, uploads each as a CSV. Cloud Run Job daily at 04:00.
  - `gtfs_rt.py` — Long-running daemon; polls GTFS-RT vehicle positions every 30 seconds; writes raw protobuf + NDJSON to GCS. Cloud Run Service (always-on, `min_instance_count=1`). Starts an HTTP server on `:8080` for Cloud Run health probes.
- [spark_jobs/](spark_jobs/) — PySpark + Delta Lake processing jobs on ephemeral Dataproc clusters (placeholder).
- [dbt_bigquery/](dbt_bigquery/) — SQL transformations. Source `raw_cdmx` → staging views → marts tables. Profile in `~/.dbt/profiles.yml`; dev target writes to `*_dev` datasets.
- [orchestration/](orchestration/) — Pipeline scheduling (placeholder).
- [infra/](infra/) — Terraform modules for all GCP resources (see Infrastructure section).

**Key libraries:** `httpx` + `tenacity` for HTTP with retries, `pydantic-settings` for config, `structlog` for logging, `click` for CLIs, `google-cloud-storage` for GCS writes, `gtfs-realtime-bindings` + `protobuf` for GTFS-RT parsing.

## ingestion/ patterns

Every ingestor follows the same four-step pattern: **pull → validate schema → upload to GCS → log metadata to BigQuery**.

- All settings live in `ingestion/config.py` (`Settings` class). Env vars use `CDMX_` prefix.
- HTTP clients (`CKANClient`, `GBFSClient`) delegate public methods to `@retry`-decorated private methods. `reraise=True` — callers always receive the original exception. Exponential backoff 2–10s, 3 attempts.
- `GCSUploader.upload(data, gcs_path, content_type)` is the only GCS primitive. Returns the full `gs://` URI.
- GCS paths follow Hive partitioning:
  - Daily feeds: `<source>/ingestion_date=YYYY-MM-DD/<filename>`
  - Minute feeds (EcoBici): `<source>/ingestion_ts=YYYY-MM-DDTHH-MM/<filename>`
  - 30-second feeds (GTFS-RT NDJSON + raw .pb): `<source>/ingestion_date=YYYY-MM-DD/vp_{epoch_ms}.<ext>`
- `GBFSClient` sends `Authorization: Bearer` only when `api_key` is non-empty.

**Schema validation** (`ingestion/schema_validator.py`):
- `validate_gbfs_envelope(payload, feed_name)` — checks `last_updated`, `ttl`, `data` keys.
- `validate_csv_header(data, required_cols, source)` — decodes only the header row (safe for large files), case-insensitive. Per-source required columns are constants in the same module (`GTFS_STATIC_REQUIRED`, `METRO_AFFLUENCE_REQUIRED`).
- Raises `ValueError` on missing columns. The ingestor's `except Exception` catches this, marks `status="error"`, and re-raises so the process exits non-zero.

**Ingestion logging** (`ingestion/bq_logger.py`):
- `RunResult` dataclass holds `source`, `run_id` (UUID4), `file_count`, `byte_count`, `row_count`, `status`, `error_message`, `ingested_at`.
- `IngestionLogger.log(result)` streams one row to `meta_cdmx.ingestion_log` via `insert_rows_json`. Wraps the call in `try/except` — a logging failure (e.g. table not yet provisioned) is warned but never propagates.
- Every `run()` function wraps its body in `try/except/finally`: the `finally` block always calls `bq_logger.log(result)`, so a row is written regardless of success or failure.
- GTFS-RT daemon emits one `RunResult` per poll (source `"metrobus_gtfs_rt"`), swallows per-poll exceptions, and continues the loop.

**GTFS-RT specifics** (`ingestion/metrobus/gtfs_rt.py`):
- `_fetch_protobuf(url, timeout, max_retries)` uses tenacity via a nested `@retry`-decorated inner function — consistent with `CKANClient` / `GBFSClient` backoff (2–10s, reraise).
- `_parse_to_ndjson(feed, snapshot_ts)` takes an already-parsed `gtfs_realtime_pb2.FeedMessage`, not raw bytes — avoids double-parsing. Returns one JSON line per `FeedEntity` with `_snapshot_ts` injected; uses `MessageToDict(preserving_proto_field_name=True)` for snake_case keys.

## dbt

- `dbt_project.yml` is at `dbt_bigquery/` root.
- Model layers: `staging/` → views in `staging_cdmx`, `intermediate/` → ephemeral, `marts/` → tables in `marts_cdmx`.
- Source definitions live in `dbt_bigquery/models/staging/sources.yml`.
- EcoBici staging uses `JSON_QUERY_ARRAY(data, '$.stations') + UNNEST` to explode the GBFS stations array out of the native BigQuery `JSON` column.
- Metrobús vehicle positions staging uses `json_value(vehicle, '$.path')` and `safe_cast()` to extract fields from the NDJSON `vehicle` JSON column.
- The `mart_metrobus_vehicle_positions_hourly` mart is partitioned by `hour` (TIMESTAMP, hourly granularity) and clustered on `route_id` to support Tableau route-level filtering efficiently.
- Run dbt commands from inside `dbt_bigquery/`.

## SQL Linting

`.sqlfluff` at the repo root configures sqlfluff. The project uses aligned-column formatting (extra spaces before `as` for readability) which conflicts with several default rules; those are excluded:

```
exclude_rules = LT01, LT02, LT05, LT13, ST06, ST07, RF04
```

Do not add `# noqa: sqlfluff` suppressions in individual SQL files — update `.sqlfluff` instead if a new rule conflicts.

## Infrastructure (Terraform)

State is stored in GCS bucket `cdmx-mobility-tfstate`. Terraform 1.9.5, Google Provider 6.5.0.

Always use the tvars file:

```bash
cd infra/
terraform init
terraform plan -var-file="terraform.tvars"
terraform apply -var-file="terraform.tvars"
```

**Provisioned resources:**
- `module.storage` — GCS bucket `cdmx-mobility-data` with lifecycle rules:
  - `raw/` prefix: move to COLDLINE after 90 days
  - `staging/` prefix: delete after 7 days
  - `metrobus/vehicle_positions_raw/` prefix: move to NEARLINE after 30 days (high-volume protobuf)
- `module.bigquery` — 4 datasets + 10 external tables + 1 native table:
  - EcoBici: `ecobici_station_status` (NDJSON), `ecobici_station_information` (NDJSON), `ecobici_system_alerts` (NDJSON)
  - Metrobús static (CSV, `for_each` resource): `metrobus_stops`, `metrobus_routes`, `metrobus_trips`, `metrobus_stop_times`, `metrobus_calendar`, `metrobus_shapes`
  - Metrobús RT: `metrobus_vehicle_positions` (NDJSON, `vehicle` column typed `JSON`)
  - Pipeline metadata: `meta_cdmx.ingestion_log` — native table, DAY-partitioned on `ingested_at`; schema: `source, run_id, file_count, byte_count, row_count, status, error_message, ingested_at`. Written by every ingestor run. **Requires `terraform apply` before first ingestor run** — until applied, `IngestionLogger` warns and continues.
- `module.iam` — service account `cdmx-pipeline-sa`, WIF pool for GitHub Actions
- `module.cloudrun` — Artifact Registry repo `ingestor` + 2 Cloud Run Jobs + 1 Cloud Run Service:
  - Job `ecobici-ingest` — triggered by Cloud Scheduler
  - Job `metrobus-gtfs-static` — triggered by Cloud Scheduler
  - Service `metrobus-gtfs-rt-daemon` — always-on (`min_instance_count=1`, `INGRESS_TRAFFIC_INTERNAL_ONLY`), startup + liveness probes on `:8080/healthz`
  - Alert policy: fires if daemon has 0 healthy instances for 5 minutes
- `module.scheduler` — 2 Cloud Scheduler jobs:
  - `ecobici-gbfs-poll` — `*/2 * * * *`, America/Mexico_City
  - `metrobus-gtfs-static-daily` — `0 4 * * *`, America/Mexico_City
- `module.secrets` — Secret Manager: `ecobici_api_key`, `tableau_pat`, `slack_webhook_url`, `metro_cdmx_rss_url`
- `module.dataproc` — Dataproc workflow template (placeholder)

**Note:** `metrobus_gtfs_rt_vehicle_positions_url` in `terraform.tvars` is currently empty. Set it before applying the cloudrun module once the SEMOVI endpoint is confirmed.

## Container Image

The ingestor Docker image is built from [Dockerfile](Dockerfile) at the repo root. All three batch ingestors (metro affluence, EcoBici GBFS, Metrobús GTFS static) and the GTFS-RT daemon use the same image — the CLI command argument selects behaviour.

- Registry: `us-central1-docker.pkg.dev/cdmx-mobility-prod/ingestor/ingestor`
- Built and pushed by the `build-and-push` CI job on every push to `main`

To build and push manually:
```bash
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
docker build -t us-central1-docker.pkg.dev/cdmx-mobility-prod/ingestor/ingestor:latest .
docker push us-central1-docker.pkg.dev/cdmx-mobility-prod/ingestor/ingestor:latest
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `CDMX_GCP_PROJECT_ID` | — | Required; GCP project ID |
| `CDMX_RAW_BUCKET_NAME` | `cdmx-mobility-raw` | GCS raw landing bucket |
| `CDMX_METRO_CKAN_BASE_URL` | `https://datos.cdmx.gob.mx/api/3/action` | CKAN API base (shared by metro affluence and Metrobús static) |
| `CDMX_METRO_AFFLUENCE_DATASET_ID` | `afluencia-diaria-del-metro-cdmx` | CKAN dataset slug for metro affluence |
| `CDMX_ECOBICI_GBFS_BASE_URL` | `https://gbfs.mex.lyftbikes.com/gbfs/es` | EcoBici GBFS feed root |
| `CDMX_ECOBICI_API_KEY` | `""` | GBFS bearer token (not required — feed is public) |
| `CDMX_ECOBICI_POLL_FEEDS` | `["station_information","station_status","system_alerts"]` | Feeds to poll per run |
| `CDMX_METROBUS_GTFS_STATIC_DATASET_ID` | `gtfs` | CKAN dataset slug for SEMOVI unified CDMX GTFS ZIP |
| `CDMX_METROBUS_GTFS_RT_VEHICLE_POSITIONS_URL` | `""` | GTFS-RT vehicle positions endpoint; obtain from SEMOVI operations |
| `CDMX_METROBUS_GTFS_RT_POLL_INTERVAL_SECONDS` | `30` | Polling interval for the RT daemon |
| `CDMX_HTTP_TIMEOUT_SECONDS` | `30` | HTTP client timeout (all ingestors) |
| `CDMX_HTTP_MAX_RETRIES` | `3` | Max retry attempts (all ingestors) |

GCP credentials via Application Default Credentials: `gcloud auth application-default login`.

## CI/CD

`.github/workflows/ci.yml` runs on every PR and push to `main`:
- `lint-and-test` — ruff, black, sqlfluff, pytest (all branches)
- `terraform-validate` — fmt check + validate (all branches)
- `gcp-auth-smoke-test` — WIF auth verification (main only)
- `ingest-metro` — runs metro affluence ingestor (main only, after `lint-and-test`)
- `ingest-metrobus-static` — runs Metrobús GTFS static ingestor (main only, after `lint-and-test`)
- `build-and-push` — builds Docker image, pushes to Artifact Registry (main only, after `lint-and-test`)

The EcoBici ingestor and Metrobús GTFS-RT daemon are **not** run in CI — they run continuously via Cloud Scheduler / always-on Cloud Run Service.

Required GitHub secrets: `WIF_PROVIDER`, `GCP_SERVICE_ACCOUNT`.

## Live Data Status

Metro affluence ingestion first ran successfully on 2026-04-18. Data accumulates at:
```
gs://cdmx-mobility-raw/metro/affluence/ingestion_date=YYYY-MM-DD/afluenciastc_simple_MM_YYYY.csv
gs://cdmx-mobility-raw/metro/affluence/ingestion_date=YYYY-MM-DD/afluenciastc_desglosado_MM_YYYY.csv
```

EcoBici ingestion has been live since 2026-04-17. Data accumulates at:
```
gs://cdmx-mobility-data/ecobici/station_status/ingestion_ts=YYYY-MM-DDTHH-MM/station_status.json
gs://cdmx-mobility-data/ecobici/station_information/ingestion_date=YYYY-MM-DD/station_information.json
gs://cdmx-mobility-data/ecobici/system_alerts/ingestion_ts=YYYY-MM-DDTHH-MM/system_alerts.json
```

Metrobús GTFS-RT daemon is implemented but the Cloud Run Service is **not yet deployed** — `metrobus_gtfs_rt_vehicle_positions_url` is empty in `terraform.tvars`. Once the SEMOVI endpoint is obtained:
1. Set `metrobus_gtfs_rt_vehicle_positions_url` in `infra/terraform.tvars`
2. `terraform apply -var-file="terraform.tvars"` to deploy the Service
3. Verify daemon health: `gcloud run services describe metrobus-gtfs-rt-daemon --region=us-central1`

Check scheduler and job health:
```bash
# EcoBici Cloud Run Job executions
gcloud run jobs executions list --job=ecobici-ingest --project=cdmx-mobility-prod --region=us-central1 --limit=5

# Metrobús static Cloud Run Job executions
gcloud run jobs executions list --job=metrobus-gtfs-static --project=cdmx-mobility-prod --region=us-central1 --limit=5

# Metrobús RT daemon instances
gcloud run services describe metrobus-gtfs-rt-daemon --project=cdmx-mobility-prod --region=us-central1
```
