# ingestion/bq_logger.py

## What it does

Provides lightweight observability for every ingestion run. Two classes work together:

### `RunResult` (dataclass)

Captures metadata about a single ingestion execution:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `source` | `str` | required | Which ingestor ran (e.g. `"metro_affluence"`, `"ecobici_station_status"`) |
| `run_id` | `str` | `uuid4()` | Unique identifier for the run |
| `file_count` | `int` | `0` | Number of GCS objects written |
| `byte_count` | `int` | `0` | Total bytes uploaded |
| `row_count` | `Optional[int]` | `None` | Logical rows processed (stations, CSV rows, protobuf entities) |
| `status` | `str` | `"success"` | `"success"` or `"error"` |
| `error_message` | `Optional[str]` | `None` | Exception message when `status == "error"` |
| `ingested_at` | `datetime` | `utcnow()` | Timestamp when the run completed |

### `IngestionLogger`

Writes one `RunResult` row to `{project_id}.meta_cdmx.ingestion_log` in BigQuery using `insert_rows_json`. Logging failures are silently swallowed (warns via `structlog`) so a BQ table outage or pre-Terraform state never kills an ingestion run.

## Tools used

- **[google-cloud-bigquery](https://cloud.google.com/python/docs/reference/bigquery/latest)** — `bigquery.Client.insert_rows_json()` for streaming insert.
- **[structlog](https://www.structlog.org/)** — Structured warning logs if the BQ insert fails.
- **`uuid`** + **`datetime`** — Standard library; generate `run_id` and `ingested_at` defaults.
- **`dataclasses`** — `@dataclass` with `field(default_factory=...)` for mutable defaults.

## How it ties with the rest of the project

- **[ingestion/metro/affluence.py](metro/affluence.py)** — Creates a `RunResult(source="metro_affluence")`, populates metrics, calls `bq_logger.log(result)` in a `finally` block.
- **[ingestion/ecobici/gbfs.py](ecobici/gbfs.py)** — One `RunResult` per feed (e.g. `"ecobici_station_status"`), logged per iteration.
- **[ingestion/metrobus/gtfs_static.py](metrobus/gtfs_static.py)** — One `RunResult(source="metrobus_gtfs_static")` per run.
- **[ingestion/metrobus/gtfs_rt.py](metrobus/gtfs_rt.py)** — One `RunResult(source="metrobus_gtfs_rt")` per 30-second poll cycle.
- **[infra/modules/bigquery/main.tf](../infra/modules/bigquery/main.tf)** — Provisions the `meta_cdmx` dataset and `ingestion_log` native table (DAY-partitioned on `ingested_at`) that receives these rows.
- **[tests/ingestion/test_bq_logger.py](../tests/ingestion/test_bq_logger.py)** — Unit tests covering default values, UUID uniqueness, BQ insert path, and error swallowing.
