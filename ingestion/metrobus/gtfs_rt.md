# ingestion/metrobus/gtfs_rt.py

## What it does

Implements a **long-running daemon** that continuously polls the SEMOVI Metrobús GTFS-RT vehicle positions endpoint, writing two GCS artifacts per poll cycle (raw protobuf + NDJSON conversion). Designed to run as an **always-on Cloud Run Service** (`min_instance_count=1`).

### Key components

#### `_fetch_protobuf(url, timeout, max_retries)`

Downloads raw protobuf bytes from the GTFS-RT endpoint. Uses a `@retry`-decorated inner function with exponential backoff (2-10s, up to `max_retries` attempts, `reraise=True`).

#### `_parse_to_ndjson(feed, snapshot_ts)`

Pure converter: takes a parsed `FeedMessage` and returns NDJSON bytes — one JSON line per `FeedEntity`. Uses `MessageToDict(preserving_proto_field_name=True)` for snake_case keys. Injects `_snapshot_ts` into every line for temporal context.

#### `_HealthHandler` + `_start_health_server(port=8080)`

Minimal `http.server.HTTPServer` that responds `200 ok` to any GET request. Started in a **daemon thread** so it doesn't block the poll loop. Required by Cloud Run for startup and liveness probes. Internal-only (GCP internal networking, `INGRESS_TRAFFIC_INTERNAL_ONLY`).

#### `run(settings)`

Main loop:
1. Starts the health server on `:8080`.
2. Creates `GCSUploader` and `IngestionLogger`.
3. Enters an infinite `while True` loop:
   - Fetches raw protobuf via `_fetch_protobuf`.
   - Parses with `gtfs_realtime_pb2.FeedMessage.ParseFromString()`.
   - Uploads raw `.pb` to `metrobus/vehicle_positions_raw/ingestion_date=YYYY-MM-DD/vp_{epoch_ms}.pb`.
   - Converts to NDJSON and uploads to `metrobus/vehicle_positions/ingestion_date=YYYY-MM-DD/vp_{epoch_ms}.ndjson`.
   - Logs `RunResult` per cycle.
   - **Swallows per-poll exceptions** — a single bad poll does not kill the process. `log.exception` captures the full traceback.
   - Sleeps for `metrobus_gtfs_rt_poll_interval_seconds` (default 30s).

At 30-second intervals this produces ~2,880 file pairs/day.

### GCS path patterns

| Artifact | Path |
|---|---|
| Raw protobuf | `metrobus/vehicle_positions_raw/ingestion_date=YYYY-MM-DD/vp_{epoch_ms}.pb` |
| NDJSON (BigQuery-ready) | `metrobus/vehicle_positions/ingestion_date=YYYY-MM-DD/vp_{epoch_ms}.ndjson` |

## Tools used

- **[httpx](https://www.python-httpx.org/)** — HTTP client for protobuf download.
- **[tenacity](https://tenacity.readthedocs.io/)** — Retry decorator on `_fetch_protobuf`.
- **[google.transit.gtfs_realtime_pb2](https://github.com/MobilityData/gtfs-realtime-bindings)** — GTFS-RT protobuf message class.
- **[google.protobuf.json_format.MessageToDict](https://googleapis.dev/python/protobuf/latest/)** — Protobuf → dict with `preserving_proto_field_name=True`.
- **`http.server`** + **`threading`** — Standard library; minimal health server in a daemon thread.
- **[ingestion/gcs_uploader.py](../gcs_uploader.py)** — GCS writes.
- **[ingestion/bq_logger.py](../bq_logger.py)** — Per-cycle ingestion metrics to BigQuery.
- **[structlog](https://www.structlog.org/)** — Structured logging.

## How it ties with the rest of the project

- **[main.py](../../main.py)** — `run-metrobus-gtfs-rt-daemon` CLI command calls `gtfs_rt.run(settings)`.
- **[infra/modules/cloudrun/main.tf](../../infra/modules/cloudrun/main.tf)** — Cloud Run Service `metrobus-gtfs-rt-daemon` with `min_instance_count=1`, health probes on `:8080/healthz`, and a monitoring alert if zero healthy instances for 5 minutes.
- **[infra/modules/storage/main.tf](../../infra/modules/storage/main.tf)** — `metrobus/vehicle_positions_raw/` prefix has a lifecycle rule: move to NEARLINE after 30 days (high-volume archival).
- **[infra/modules/bigquery/main.tf](../../infra/modules/bigquery/main.tf)** — External table `metrobus_vehicle_positions` reads from `metrobus/vehicle_positions/ingestion_date=*/*.ndjson`. The `vehicle` column is typed `JSON`.
- **[dbt_bigquery/models/staging/stg_metrobus_vehicle_positions.sql](../../dbt_bigquery/models/staging/stg_metrobus_vehicle_positions.sql)** — Flattens the NDJSON `vehicle` JSON column into typed columns.
- **[tests/ingestion/metrobus/test_gtfs_rt.py](../../tests/ingestion/metrobus/test_gtfs_rt.py)** — Unit tests for `_parse_to_ndjson`, `_fetch_protobuf`, health server, and the daemon loop's error resilience.

> **Status:** Cloud Run Service is implemented but not yet deployed — `metrobus_gtfs_rt_vehicle_positions_url` is empty in `infra/terraform.tvars`. Set it once the SEMOVI endpoint is confirmed.
