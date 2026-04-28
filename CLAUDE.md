# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`cdmx-mobility` is a GCP-based data engineering platform for Mexico City mobility data. It follows a medallion architecture: raw ingestion → Spark Bronze→Silver → dbt Gold models in BigQuery → Tableau dashboards.

GCP project ID: `cdmx-mobility-prod`.
GCS data bucket: `cdmx-mobility-data`.
GCS raw bucket (metro affluence only): `cdmx-mobility-raw`.

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
uv run ruff format .

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

# Spark Silver jobs — local smoke test against real GCS data
# Download Bronze slice first, then run with -m (required for ingestion imports):
CDMX_GCP_PROJECT_ID=cdmx-mobility-prod uv run python -m spark_jobs.bronze_to_silver_ecobici --local \
  --input-path "/tmp/bronze/ecobici/status/*.json" \
  --info-input "/tmp/bronze/ecobici/info/*.json" \
  --output-path /tmp/silver/ecobici

CDMX_GCP_PROJECT_ID=cdmx-mobility-prod uv run python -m spark_jobs.bronze_to_silver_metro_affluence --local \
  --input-path "/tmp/bronze/metro/affluence_simple/ingestion_date=*/*.csv" \
  --output-path /tmp/silver/metro

CDMX_GCP_PROJECT_ID=cdmx-mobility-prod uv run python -m spark_jobs.bronze_to_silver_weather --local \
  --input-path "/tmp/bronze/weather/*.json" \
  --output-path /tmp/silver/weather

CDMX_GCP_PROJECT_ID=cdmx-mobility-prod uv run python -m spark_jobs.bronze_to_silver_metrobus_vehicles --local \
  --input-path "/tmp/bronze/metrobus/positions/" \
  --stops-input "/tmp/bronze/metrobus/stops/ingestion_date=*/stops.csv" \
  --output-path /tmp/silver/metrobus

# All four jobs also accept --input-date YYYY-MM-DD to scope the Bronze GCS glob
# to a single partition — used by Airflow for date-specific runs and backfills.

# Note: use `python -m spark_jobs.<job>` not `python spark_jobs/<job>.py`.
# The latter adds spark_jobs/ to sys.path and breaks the `ingestion` import.

# Airflow VM (access via IAP tunnel)
make airflow-up        # docker compose up on the VM
make airflow-down      # docker compose down
make airflow-logs      # tail scheduler + webserver logs
make airflow-status    # show running containers

# Open a local tunnel then browse to http://localhost:8080
gcloud compute ssh cdmx-airflow --tunnel-through-iap --project=cdmx-mobility-prod \
  --zone=us-central1-a -- -L 8080:localhost:8080

# Backfill a single missed day (opens IAP tunnel, POSTs to Airflow REST API)
make backfill DATE=2026-03-15

# Backfill a date range
make backfill-range START=2026-03-01 END=2026-03-15

# dbt (run from dbt_bigquery/)
cd dbt_bigquery/
uv run dbt deps                                        # install packages first (dbt_date, dbt_expectations, dbt_utils)
uv run dbt build                                       # full build: seed + run + test
uv run dbt seed --target prod                          # load reference data to seeds_cdmx
uv run dbt snapshot --target prod                      # update SCD2 snapshot in snapshots_cdmx
uv run dbt run --target prod --exclude "example"       # materialize all Gold models
uv run dbt run --target prod --select fct_ecobici_station_hourly --full-refresh  # full rebuild of incremental model
uv run dbt test --target prod                          # run all data quality tests
```

## Architecture

```
datos.cdmx.gob.mx (CKAN)           sinopticoplus email         Lyft GBFS
  │  afluencia-diaria-del-metro-cdmx   │ (SendGrid inbound)       │
  │                                    │  RT .proto + static .zip │
  │                                    │                          │
  ▼                                    ▼                          ▼
ingestion/metro/            ingestion/metrobus/          ingestion/ecobici/
 affluence.py                inbound_webhook.py  gtfs_rt.py  gbfs.py
 CKANClient                  (Cloud Run Service, (not deployed) GBFSClient
 (CI, daily cron,             public ingress)               (Cloud Run Job,
  exits cleanly on                │                          every 10 min)
  CKAN timeout)                   │ archives RT + static ZIP
                                  ▼
                    gs://cdmx-mobility-data/
                      metrobus/gtfs_static_email/ingestion_date=YYYY-MM-DD/  ← raw ZIP (once/day)
                      metrobus/vehicle_positions/ingestion_date=YYYY-MM-DD/  ← NDJSON
                      metrobus/vehicle_positions_raw/ingestion_date=YYYY-MM-DD/ ← .pb archival
                                  │
                    gtfs_static.py (Cloud Run Job, daily 04:00)
                    reads most recent ZIP from gtfs_static_email/,
                    unpacks 6 feeds → metrobus/static/{feed}/ingestion_date=YYYY-MM-DD/
  │                               │               │               │
  ▼                               ▼               ▼               ▼
gs://cdmx-mobility-raw/     gs://cdmx-mobility-data/
  metro/affluence_simple/     metrobus/static/{feed}/ingestion_date=YYYY-MM-DD/
  ingestion_date=YYYY-MM-DD/  metrobus/vehicle_positions/ingestion_date=YYYY-MM-DD/
  metro/affluence_desglosado/ ecobici/station_status/ingestion_ts=YYYY-MM-DDTHH-MM/
  ingestion_date=YYYY-MM-DD/  ecobici/station_information/ingestion_date=YYYY-MM-DD/
                              ecobici/system_alerts/ingestion_ts=YYYY-MM-DDTHH-MM/
                              weather/hourly/ingestion_date=YYYY-MM-DD/
  │
  ▼  (Spark on ephemeral Dataproc — triggered by Airflow daily_mobility_pipeline DAG)
spark_jobs/
  bronze_to_silver_ecobici.py          → silver/ecobici/state_changes/ + station_master/
  bronze_to_silver_metro_affluence.py  → silver/metro/affluence_daily/
  bronze_to_silver_metrobus_vehicles.py→ silver/metrobus/stop_events/
  bronze_to_silver_weather.py          → silver/weather/hourly_fact/
  │
  ▼  (BigQuery external tables in silver_cdmx)
dbt_bigquery/models/staging/
  stg_silver_ecobici_state_changes.sql
  stg_silver_ecobici_station_master.sql
  stg_silver_metro_affluence.sql
  stg_silver_metrobus_stop_events.sql
  stg_silver_weather_hourly.sql
  stg_ecobici_station_{status,information}.sql   ← Bronze; feeds legacy mart only
  stg_metrobus_{stops,routes,vehicle_positions}.sql
  │
  ▼
dbt_bigquery/models/intermediate/
  int_ecobici_station_hourly_agg.sql    (ephemeral)
  int_weather_city_hourly.sql           (ephemeral)
  │
  ▼
dbt_bigquery/models/marts/
  core/
    dim_date.sql                        ← 2,555 rows, 7-year calendar with CDMX flags
    dim_station.sql                     ← 8,011 rows, all EcoBici + Metro + Metrobús stops
    dim_weather_condition.sql           ← 5 rows, comfort score lookup (seed)
  mobility/
    fct_ecobici_station_hourly.sql      ← 1.4M rows, incremental merge, partitioned by service_date
    fct_metro_affluence_daily.sql       ← 1.16M rows, 2010–2026, partitioned by month
    fct_metrobus_stop_events.sql        ← 74.6K rows, partitioned by service_date
    fct_unified_mobility_hourly.sql     ← 1.4M rows, all modes + weather, primary Tableau source
  mart_ecobici_availability_2min.sql    ← 2.5M rows, legacy 2-min snapshot mart
  mart_metrobus_vehicle_positions_hourly.sql ← 159K rows, legacy hourly mart
  │
  ▼
snapshots_cdmx/
  ecobici_station_snapshot             ← 7.4K rows, SCD2 station history
  │
  ▼
Tableau (reads from marts_cdmx — primary table: fct_unified_mobility_hourly)
```

**Modules:**
- [ingestion/](ingestion/) — HTTP ingestors. Config via Pydantic settings (`ingestion/config.py`, `CDMX_` env prefix). Primitives: `CKANClient`, `GBFSClient`, `GCSUploader`, `IngestionLogger` / `RunResult` (BQ metadata), `validate_csv_header` / `validate_gbfs_envelope` (schema validation).
- [ingestion/metro/](ingestion/metro/) — Metro affluence ingestor. One-shot batch, runs in CI daily cron (06:00 CDMX). CKAN dataset: `afluencia-diaria-del-metro-cdmx`. Uploads `afluenciastc_simple_*.csv` to `metro/affluence_simple/` and `afluenciastc_desglosado_*.csv` to `metro/affluence_desglosado/` — separate GCS prefixes so BigQuery external tables can use a single wildcard per table. Exits cleanly with `status=skipped` when `datos.cdmx.gob.mx` is unreachable.
- [ingestion/ecobici/](ingestion/ecobici/) — EcoBici GBFS ingestor (`station_status`, `station_information`, `system_alerts`). Cloud Run Job every 10 minutes.
- [ingestion/metrobus/](ingestion/metrobus/) — Three ingestors:
  - `gtfs_static.py` — Reads the most recent static GTFS ZIP from `metrobus/gtfs_static_email/` in GCS (archived by the webhook), unpacks 6 standard feeds, uploads each as CSV to `metrobus/static/{feed}/`. No longer calls CKAN. Cloud Run Job daily at 04:00.
  - `gtfs_rt.py` — Polling daemon code (not deployed). Retained in the repo if a direct SEMOVI GTFS-RT URL is ever obtained.
  - `inbound_webhook.py` — FastAPI service receiving GTFS data from sinopticoplus via SendGrid inbound parse. Cloud Run Service (`metrobus-gtfs-inbound`, public ingress). Processes RT `.proto` files → NDJSON + raw `.pb` to GCS. Also archives the static GTFS ZIP (`Metrobus_GTFS_ESTATICO.zip`) once per day with a dedup check. **Active source for both RT vehicle positions and static GTFS.**
- [spark_jobs/](spark_jobs/) — Four PySpark Bronze→Silver jobs running on ephemeral Dataproc clusters. Each job accepts `--input-path`, `--output-path`, and `--local` (local[2] for smoke tests). Imports from `ingestion/` for BQ logging; must be invoked as `python -m spark_jobs.<job>` to resolve imports correctly.
  - `conformance/` — Shared utilities: `spark_session.py`, `time_utils.py` (UTC→CDMX service_date), `station_names.py` (metro station name canonicalization), `h3_utils.py` (spatial stop snapping).
- [dbt_bigquery/](dbt_bigquery/) — SQL transformations. Silver→Gold layer is fully implemented and live. Sources: `raw_cdmx` (Bronze) and `silver_cdmx` (Silver Parquet). `generate_schema_name` macro in `macros/` ensures prod writes to clean dataset names (`staging_cdmx`, `marts_cdmx`, etc.) without target prefix. Profile in `~/.dbt/profiles.yml`; dev target writes to `*_dev` datasets.
- [orchestration/](orchestration/) — Self-hosted Airflow 2.9.3 on a GCE e2-standard-2 VM (`cdmx-airflow`). Three DAGs: `daily_mobility_pipeline` (08:00 UTC, ingest → sensors → Spark Silver → dbt build/test → Slack notify), `hourly_realtime_pipeline` (:05 past each hour, EcoBici only), `weekly_backfill_check` (Sunday 09:00, Great Expectations quality report). Config externalized to `orchestration/airflow/config/*.yml`. Docker Compose stack (postgres + scheduler + webserver) managed by `orchestration/docker-compose.yml`. VM bootstrapped via `infra/modules/airflow_vm/startup.sh`; DAGs synced from GitHub every 5 min via cron. Access via IAP TCP tunnel only — port 8080 never exposed publicly.
- [infra/](infra/) — Terraform modules for all GCP resources (see Infrastructure section).
- [docs/](docs/) — `cost-estimates.md` (~$58/month steady state), `adr/002-spark-for-bronze-to-silver.md`.

**Key libraries:** `httpx` + `tenacity` for HTTP with retries, `pydantic-settings` for config, `structlog` for logging, `click` for CLIs, `google-cloud-storage` for GCS writes, `gtfs-realtime-bindings` + `protobuf` for GTFS-RT parsing, `pyspark` for Silver transforms, `h3` for spatial indexing.

## ingestion/ patterns

Every ingestor follows the same four-step pattern: **pull → validate schema → upload to GCS → log metadata to BigQuery**.

- All settings live in `ingestion/config.py` (`Settings` class). Env vars use `CDMX_` prefix.
- HTTP clients (`CKANClient`, `GBFSClient`) delegate public methods to `@retry`-decorated private methods. `reraise=True` — callers always receive the original exception. Exponential backoff 2–10s, 3 attempts.
- `GCSUploader.upload(data, gcs_path, content_type)` uploads bytes and returns the full `gs://` URI. `GCSUploader.exists(gcs_path)` checks blob existence (used for static ZIP daily dedup).
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

## Spark Jobs

Four Bronze→Silver jobs in `spark_jobs/`. Each follows the same pattern: read Bronze GCS → transform → write partitioned Parquet to `gs://cdmx-mobility-data/silver/` → log `RunResult` to BQ.

| Job | Input | Output | Partition |
|---|---|---|---|
| `bronze_to_silver_ecobici.py` | `ecobici/station_status/` + `station_information/` | `silver/ecobici/state_changes/` + `station_master/` | `service_date` |
| `bronze_to_silver_metro_affluence.py` | `metro/affluence_simple/` (raw bucket) | `silver/metro/affluence_daily/` | `service_date` |
| `bronze_to_silver_metrobus_vehicles.py` | `metrobus/vehicle_positions/` + `metrobus/static/stops/` | `silver/metrobus/stop_events/` | `service_date`, `route_id` |
| `bronze_to_silver_weather.py` | `weather/hourly/` | `silver/weather/hourly_fact/` | `service_date` |

**Key design notes:**
- EcoBici deduplication: `lag()` window over `(station_id ORDER BY snapshot_ts)` keeps only rows where at least one field changed (~6-9× compression).
- Metro affluence: the `afluenciastc_simple_*.csv` file contains one aggregate daily total per `(fecha, linea, estacion)` — no payment-type breakdown. The `afluenciastc_desglosado_*.csv` (7 columns: fecha, mes, anio, linea, estacion, tipo_pago, afluencia) is archived to `metro/affluence_desglosado/` but has no Silver pipeline yet. BigQuery does not support two wildcards in a single external table URI, which is why simple and desglosado files must be in separate GCS prefixes.
- Metrobús stop snapping: H3 resolution 9 (~174 m hexagons) inner-joins positions to stops; dwell sessions are contiguous at-stop observations with gap ≤ 60s and duration ≥ 30s.
- Weather: Open-Meteo hourly arrays are pivoted from one row per coordinate to one row per UTC hour with 5 × 4 coordinate columns + city-wide averages + derived features (Rothfusz heat index, comfort score, Beaufort wind category).
- **Weather per-zone (not yet implemented):** Silver `weather_hourly_fact` contains 20 per-coordinate columns named `{coord}_{metric}` (e.g. `centro_temperature_2m`, `norte_windspeed_10m`). The dbt layer currently only uses city-wide `avg_*` columns. To link weather zones to stations: (1) expose per-coordinate columns in a new `stg_silver_weather_per_coordinate.sql`; (2) build a `dim_weather_zone` seed; (3) assign each station in `dim_station` to its nearest zone using `ST_DISTANCE`; (4) join `fct_unified_mobility_hourly` on `(obs_hour, weather_zone)`.
- **`wind_category` is a STRING**, not an integer: values are `'calm'` (< 1.5 m/s), `'breeze'` (1.5–10.7 m/s), `'strong'` (≥ 10.7 m/s). Use `wind_category = 'strong'` in SQL, not `wind_category >= 6`.
- `_silver_stats()` returns `(0, 0)` for local paths — avoids GCS API calls in `--local` mode.
- ADR: `docs/adr/002-spark-for-bronze-to-silver.md` documents the choice of Spark over BigQuery SQL and plain Parquet over Delta Lake.

## dbt

- `dbt_project.yml` is at `dbt_bigquery/` root.
- Model layers: `staging/` → views in `staging_cdmx`, `intermediate/` → ephemeral, `marts/` → tables in `marts_cdmx`, seeds → `seeds_cdmx`, snapshots → `snapshots_cdmx`.
- The `generate_schema_name` macro in `macros/` controls dataset naming: in prod it uses the custom schema name directly (e.g. `staging_cdmx`); in dev it prepends the target schema (e.g. `dev_staging_cdmx`). Without this macro dbt default behaviour would create `marts_cdmx_staging_cdmx` etc. in prod.
- Always run `dbt deps` before `dbt parse` or `dbt build` — packages (`dbt_date`, `dbt_expectations`, `dbt_utils`) must be installed first.
- Sources: `raw_cdmx` (Bronze external tables — EcoBici, Metrobús static + RT) and `silver_cdmx` (Silver Parquet external tables). Metro affluence Bronze source (`raw_cdmx.metro_affluence`) exists in BigQuery but is not consumed by any dbt model — the Gold layer reads Silver only.
- `fct_ecobici_station_hourly` is an incremental model using `merge` strategy on `(station_id, hour_ts)`. It deduplicates with `QUALIFY ROW_NUMBER()` to handle the edge case where the same `obs_hour` spans two `service_date` values at the CDMX midnight boundary. Use `--full-refresh` when rebuilding from scratch.
- `fct_metro_affluence_daily` uses monthly partition granularity (`granularity: 'month'`) — the Silver dataset covers 2010–2026 (~5,800 days), which would exceed BigQuery's 4,000-partition limit with daily granularity. Monthly gives ~195 partitions.
- The `mart_ecobici_availability_2min` and `mart_metrobus_vehicle_positions_hourly` are legacy marts kept for backwards compatibility. The canonical Gold tables are the `fct_*` models.
- EcoBici staging uses `JSON_QUERY_ARRAY(data, '$.stations') + UNNEST` to explode the GBFS stations array out of the native BigQuery `JSON` column.
- Metrobús vehicle positions staging uses `json_value(vehicle, '$.path')` and `safe_cast()` to extract fields from the NDJSON `vehicle` JSON column.
- Run dbt commands from inside `dbt_bigquery/`.
- **Weather zone granularity:** `int_weather_city_hourly` and all downstream models use city-wide `avg_*` columns. Per-zone weather is not yet implemented — see the Spark Jobs section for the full implementation path.

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
  - `silver/` prefix: move to NEARLINE after 180 days
- `module.bigquery` — datasets + external and native tables. Accepts two bucket variables: `raw_bucket_name` (`cdmx-mobility-data`) and `metro_raw_bucket_name` (`cdmx-mobility-raw`):
  - `raw_cdmx`: EcoBici (3 NDJSON tables), Metrobús static (6 CSV tables via `for_each` — `allow_jagged_rows=true`, `allow_quoted_newlines=true`), Metrobús RT (1 NDJSON table), metro affluence simple (1 CSV table pointing to `metro/affluence_simple/`)
  - `silver_cdmx`: 5 Parquet external tables (`ecobici_state_changes`, `ecobici_station_master`, `metro_affluence`, `metrobus_stop_events`, `weather_hourly_fact`) — `autodetect=false`, explicit schemas, CUSTOM Hive partitioning.
  - `meta_cdmx`: `ingestion_log` native table, DAY-partitioned on `ingested_at`.
  - `staging_cdmx`, `marts_cdmx`, `seeds_cdmx`, `snapshots_cdmx`: dbt targets
- `module.iam` — service account `cdmx-pipeline-sa`, WIF pool for GitHub Actions. Includes two bindings required for Dataproc scheduling: Cloud Scheduler service agent has `roles/iam.serviceAccountTokenCreator` on the pipeline SA; the pipeline SA has `roles/iam.serviceAccountUser` on itself (required for Dataproc cluster creation).
- `module.cloudrun` — Artifact Registry repo `ingestor` + Cloud Run resources:
  - Job `ecobici-ingest` — triggered by Cloud Scheduler every 10 min
  - Job `metrobus-gtfs-static` — triggered by Cloud Scheduler daily 04:00
  - Job `metrobus-gtfs-email-ingest` — triggered by Cloud Scheduler every 5 min (polls for new sinopticoplus emails)
  - Job `weather-ingest` — triggered by Cloud Scheduler daily 02:00
  - Service `metrobus-gtfs-inbound` — public ingress, receives GTFS NDJSON from SendGrid webhook
- `module.scheduler` — 3 Cloud Scheduler jobs: ecobici poll (every 10 min), metrobus email ingest (every 5 min), weather ingest (daily 02:00). Metrobús static Cloud Run Job also scheduled (daily 04:00). The 4 Spark Silver Dataproc jobs are **no longer triggered by Cloud Scheduler** — they are triggered by the Airflow `daily_mobility_pipeline` DAG.
- `module.secrets` — Secret Manager secrets
- `module.dataproc` — 4 Dataproc workflow templates (`cdmx-spark-ecobici`, `cdmx-spark-metro`, `cdmx-spark-metrobus`, `cdmx-spark-weather`), each with an ephemeral 1 master + 3 workers **n1-standard-2** cluster (8 vCPUs total — fits within the 10-vCPU `CPUS_ALL_REGIONS` project quota). Each template accepts an `INPUT_DATE` parameter (regex-validated `YYYY-MM-DD` or empty) passed by Airflow at instantiation. Spark job `.py` files and `spark_jobs.zip` / `ingestion.zip` are uploaded to GCS by CI on every push to `main`.
- `module.airflow_vm` — GCE e2-standard-2 VM (`cdmx-airflow`, Debian 12, 50 GB pd-balanced), static IP, IAP firewall (port 22 + 8080 from `35.235.240.0/20` only). Service account `cdmx-airflow-sa` with 8 roles: `run.invoker`, `dataproc.editor`, `dataproc.worker`, `bigquery.dataEditor`, `bigquery.jobUser`, `storage.objectAdmin`, `secretmanager.secretAccessor`, `iam.serviceAccountUser`. Secrets: `airflow-fernet-key`, `airflow-db-password`, `airflow-slack-webhook-url` (all auto-replicated).

## Container Image

The ingestor Docker image is built from [Dockerfile](Dockerfile) at the repo root. All ingestors share the same image — the CLI command argument selects behaviour. `ENV UV_NO_SYNC=1` prevents `uv run` from re-syncing the full lockfile (including dev/spark groups) at container startup.

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
| `CDMX_RAW_BUCKET_NAME` | `cdmx-mobility-raw` | GCS raw landing bucket (metro affluence only) |
| `CDMX_METRO_CKAN_BASE_URL` | `https://datos.cdmx.gob.mx/api/3/action` | CKAN API base (shared by metro affluence and Metrobús static) |
| `CDMX_METRO_AFFLUENCE_DATASET_ID` | `afluencia-diaria-del-metro-cdmx` | CKAN dataset slug for metro affluence |
| `CDMX_ECOBICI_GBFS_BASE_URL` | `https://gbfs.mex.lyftbikes.com/gbfs/es` | EcoBici GBFS feed root |
| `CDMX_ECOBICI_API_KEY` | `""` | GBFS bearer token (not required — feed is public) |
| `CDMX_ECOBICI_POLL_FEEDS` | `["station_information","station_status","system_alerts"]` | Feeds to poll per run |
| `CDMX_HTTP_TIMEOUT_SECONDS` | `30` | HTTP client timeout (all ingestors) |
| `CDMX_HTTP_MAX_RETRIES` | `3` | Max retry attempts (all ingestors) |

GCP credentials via Application Default Credentials: `gcloud auth application-default login`.

## CI/CD

`.github/workflows/ci.yml` triggers on:
- `push` to `main`
- `pull_request` (any branch)
- `schedule`: `0 12 * * *` (06:00 CDMX, UTC-6) — runs `ingest-metro` only

Jobs:
- `lint-and-test` — ruff check, ruff format --check, sqlfluff, pytest with `--group spark`. **Skipped on schedule trigger.**
- `terraform-validate` — fmt check + validate. **Skipped on schedule trigger.**
- `gcp-auth-smoke-test` — WIF auth verification. Push to main only.
- `ingest-metro` — runs metro affluence ingestor on every push to main and on the daily schedule. Exits 0 on `ConnectTimeout`/`ConnectError` (logs `status=skipped` to BQ) because `datos.cdmx.gob.mx` intermittently blocks GitHub Actions IPs.
- `build-and-push` — builds and pushes Docker image; also uploads `spark_jobs/*.py` and `spark_jobs.zip` / `ingestion.zip` to `gs://cdmx-mobility-data/code/spark_jobs/`. Push to main only, after `lint-and-test`. **Does NOT automatically redeploy Cloud Run services/jobs** — Cloud Run resolves `:latest` at deploy time, not at image push time. After CI, manually run `gcloud run services update metrobus-gtfs-inbound --image=...` and `gcloud run jobs update <job> --image=...` to roll out the new image, or make a Terraform change that touches the resource.
- `validate-dags` — installs Airflow 2.9.3 + providers, runs `airflow db init`, loads DagBag from `orchestration/airflow/dags/`, and asserts all three expected DAG IDs are present with no import errors. Runs on push and pull_request (skipped on schedule trigger).
- `dbt parse` step in CI requires `dbt deps` to run first — packages must be installed before parsing.

Required GitHub secrets: `WIF_PROVIDER`, `GCP_SERVICE_ACCOUNT`.

## Live Data Status

**Metro affluence** — one Bronze partition ingested 2026-04-18. The CSV is a cumulative historical dump covering 2010-01-01 → 2026-03-31 (1.16M rows after Silver processing). Simple file is at:
```
gs://cdmx-mobility-raw/metro/affluence_simple/ingestion_date=2026-04-18/afluenciastc_simple_03_2026.csv
gs://cdmx-mobility-raw/metro/affluence_desglosado/ingestion_date=2026-04-18/afluenciastc_desglosado_03_2026.csv
```

**EcoBici** — live since 2026-04-17. Cloud Run Job every 10 min via Cloud Scheduler.
```
gs://cdmx-mobility-data/ecobici/station_status/ingestion_ts=YYYY-MM-DDTHH-MM/station_status.json
gs://cdmx-mobility-data/ecobici/station_information/ingestion_date=YYYY-MM-DD/station_information.json
gs://cdmx-mobility-data/ecobici/system_alerts/ingestion_ts=YYYY-MM-DDTHH-MM/system_alerts.json
```

**Metrobús vehicle positions** — accumulating via the sinopticoplus email ingest path since 2026-04-19.
```
gs://cdmx-mobility-data/metrobus/vehicle_positions/ingestion_date=YYYY-MM-DD/
gs://cdmx-mobility-data/metrobus/vehicle_positions_raw/ingestion_date=YYYY-MM-DD/
```

**Metrobús GTFS static** — sinopticoplus email delivers `Metrobus_GTFS_ESTATICO.zip` alongside the RT file. Static GTFS CSVs available from 2026-04-24 onwards.
```
gs://cdmx-mobility-data/metrobus/gtfs_static_email/ingestion_date=YYYY-MM-DD/Metrobus_GTFS_ESTATICO.zip
gs://cdmx-mobility-data/metrobus/static/{feed}/ingestion_date=YYYY-MM-DD/{feed}.csv
```

**Weather** — accumulating since 2026-04-21.
```
gs://cdmx-mobility-data/weather/hourly/ingestion_date=YYYY-MM-DD/weather_*.json
```

**Silver** — live as of 2026-04-27. All four Spark jobs have run successfully. Silver data is in BigQuery via external tables in `silver_cdmx`.
```
gs://cdmx-mobility-data/silver/ecobici/state_changes/service_date=YYYY-MM-DD/
gs://cdmx-mobility-data/silver/ecobici/station_master/
gs://cdmx-mobility-data/silver/metro/affluence_daily/service_date=YYYY-MM-DD/   (2010–2026)
gs://cdmx-mobility-data/silver/metrobus/stop_events/service_date=YYYY-MM-DD/route_id=*/
gs://cdmx-mobility-data/silver/weather/hourly_fact/service_date=YYYY-MM-DD/
```

**Gold** — fully materialized as of 2026-04-27. All 19 dbt models pass. Primary Tableau source is `marts_cdmx.fct_unified_mobility_hourly`.

| Table | Rows | Notes |
|---|---|---|
| `dim_date` | 2,555 | 7-year calendar, CDMX holiday + quincena flags |
| `dim_station` | 8,011 | EcoBici + Metro + Metrobús stops, GEOGRAPHY column |
| `dim_weather_condition` | 5 | Comfort score band lookup |
| `fct_ecobici_station_hourly` | 1.4M | Incremental merge; `--full-refresh` to rebuild |
| `fct_metro_affluence_daily` | 1.16M | 2010–2026, monthly partitions |
| `fct_metrobus_stop_events` | 74.6K | Dwell events with headway |
| `fct_unified_mobility_hourly` | 1.4M | All modes + weather, primary Tableau table |
| `mart_ecobici_availability_2min` | 2.5M | Legacy Bronze mart |
| `mart_metrobus_vehicle_positions_hourly` | 159K | Legacy Bronze mart |
| `ecobici_station_snapshot` | 7.4K | SCD2 station history |

Check scheduler and job health:
```bash
# EcoBici Cloud Run Job executions
gcloud run jobs executions list --job=ecobici-ingest --project=cdmx-mobility-prod --region=us-central1 --limit=5

# Metrobús email Cloud Run Job executions
gcloud run jobs executions list --job=metrobus-gtfs-email-ingest --project=cdmx-mobility-prod --region=us-central1 --limit=5

# Metrobús static Cloud Run Job executions
gcloud run jobs executions list --job=metrobus-gtfs-static --project=cdmx-mobility-prod --region=us-central1 --limit=5

# BQ ingestion log — recent runs
bq query --project_id=cdmx-mobility-prod --use_legacy_sql=false \
  'SELECT source, status, ingested_at FROM meta_cdmx.ingestion_log ORDER BY ingested_at DESC LIMIT 20'

# Trigger a Dataproc Silver job manually
gcloud dataproc workflow-templates instantiate cdmx-spark-ecobici \
  --region=us-central1 --project=cdmx-mobility-prod
```
