# ingestion/ecobici/gbfs.py

## What it does

Polls EcoBici's GBFS feeds and lands each response as a JSON file in GCS. This is a **short-lived batch job** designed to be invoked every 2 minutes by Cloud Scheduler via a Cloud Run Job.

### Execution flow (`run(settings)`)

Iterates over each feed in `settings.ecobici_poll_feeds` (default: `station_information`, `station_status`, `system_alerts`). For each feed:

1. Creates a `GBFSClient` and a `GCSUploader`.
2. Fetches the feed JSON via `client.fetch(feed_name)`.
3. Validates the GBFS envelope (`last_updated`, `ttl`, `data` keys must be present).
4. Serializes the payload to JSON bytes.
5. Chooses the GCS path based on feed type:
   - **Static feeds** (`station_information`) → `ecobici/{feed}/ingestion_date=YYYY-MM-DD/{feed}.json`
   - **Dynamic feeds** (`station_status`, `system_alerts`) → `ecobici/{feed}/ingestion_ts=YYYY-MM-DDTHH-MM/{feed}.json`
6. Uploads to GCS with `content_type="application/json"`.
7. Sets `row_count` to the number of stations if the feed contains a `data.stations` array.
8. Logs `RunResult` to BigQuery in the `finally` block (one row per feed).

### GCS path patterns

| Feed | Path | Partition |
|---|---|---|
| `station_information` | `ecobici/station_information/ingestion_date=YYYY-MM-DD/station_information.json` | Daily |
| `station_status` | `ecobici/station_status/ingestion_ts=YYYY-MM-DDTHH-MM/station_status.json` | Per minute |
| `system_alerts` | `ecobici/system_alerts/ingestion_ts=YYYY-MM-DDTHH-MM/system_alerts.json` | Per minute |

## Tools used

- **[ingestion/gbfs_client.py](../gbfs_client.py)** — HTTP client for GBFS feeds with retry.
- **[ingestion/gcs_uploader.py](../gcs_uploader.py)** — GCS write primitive.
- **[ingestion/schema_validator.py](../schema_validator.py)** — `validate_gbfs_envelope()` checks GBFS top-level keys.
- **[ingestion/bq_logger.py](../bq_logger.py)** — Logs per-feed `RunResult` to `meta_cdmx.ingestion_log`.
- **[structlog](https://www.structlog.org/)** — Structured logging.
- **`datetime`** + **`json`** — Standard library; timestamps and JSON serialization.

## How it ties with the rest of the project

- **[main.py](../../main.py)** — `ingest-ecobici-gbfs` CLI command calls `gbfs.run(settings)`.
- **[infra/modules/cloudrun/main.tf](../../infra/modules/cloudrun/main.tf)** — Cloud Run Job `ecobici-ingest` runs this command via container.
- **[infra/modules/scheduler/main.tf](../../infra/modules/scheduler/main.tf)** — Cloud Scheduler job `ecobici-gbfs-poll` triggers the Cloud Run Job every 2 minutes (`*/2 * * * *`, America/Mexico_City).
- **[infra/modules/bigquery/main.tf](../../infra/modules/bigquery/main.tf)** — External tables `ecobici_station_status`, `ecobici_station_information`, `ecobici_system_alerts` read from the GCS paths written here.
- **[dbt_bigquery/models/staging/stg_ecobici_station_status.sql](../../dbt_bigquery/models/staging/stg_ecobici_station_status.sql)** — Unnests the `data.stations` JSON array from the raw external table.
- **[dbt_bigquery/models/staging/stg_ecobici_station_information.sql](../../dbt_bigquery/models/staging/stg_ecobici_station_information.sql)** — Unnests station metadata.
- **[tests/ingestion/ecobici/test_gbfs.py](../../tests/ingestion/ecobici/test_gbfs.py)** — Unit tests for `run()`, partitioning logic, validation, and logging.
