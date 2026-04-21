# ingestion/metrobus/gtfs_static.py

## What it does

Downloads the SEMOVI unified CDMX GTFS static ZIP archive from the CKAN open data portal, unpacks the standard GTFS feed files, validates their headers, and uploads each as a separate CSV to GCS. This is a **one-shot batch job** that runs daily at 04:00 Mexico City time.

The SEMOVI GTFS ZIP covers multiple transit operators (Metrobús, Metro, Tren Ligero, Cablebús, etc.) in a single package. Only the 6 standard GTFS feed files are processed; others (e.g., `agency.txt`, `feed_info.txt`) are skipped.

### Execution flow (`run(settings)`)

1. Initializes `IngestionLogger` and a `RunResult(source="metrobus_gtfs_static")`.
2. Creates `CKANClient` and `GCSUploader`.
3. Fetches the resource list for CKAN dataset `gtfs`.
4. Calls `_find_zip_resource(resources)` — selects the most recently modified resource whose format is `ZIP` or `GTFS`, or whose URL ends in `.zip`.
5. Downloads the ZIP bytes.
6. Opens the ZIP with `zipfile.ZipFile` and iterates over entries:
   - Skips any entry not in `_EXPECTED_FEEDS` (`stops`, `routes`, `trips`, `stop_times`, `calendar`, `shapes`).
   - Validates the CSV header for known feeds using `GTFS_STATIC_REQUIRED`.
   - Uploads each feed to `metrobus/static/{feed}/ingestion_date=YYYY-MM-DD/{feed}.csv`.
7. Accumulates `file_count`, `byte_count`, `row_count`.
8. Logs `RunResult` unconditionally in `finally`.

### GCS path pattern

```
metrobus/static/{feed_name}/ingestion_date=YYYY-MM-DD/{feed_name}.csv
```

Where `feed_name` ∈ `{stops, routes, trips, stop_times, calendar, shapes}`.

## Tools used

- **[ingestion/ckan_client.py](../ckan_client.py)** — Downloads GTFS resources from `datos.cdmx.gob.mx`.
- **[ingestion/gcs_uploader.py](../gcs_uploader.py)** — GCS write primitive.
- **[ingestion/schema_validator.py](../schema_validator.py)** — `validate_csv_header()` + `GTFS_STATIC_REQUIRED` constants.
- **[ingestion/bq_logger.py](../bq_logger.py)** — Logs `RunResult` to `meta_cdmx.ingestion_log`.
- **`zipfile`** + **`io`** + **`datetime`** — Standard library; ZIP extraction, in-memory buffer, date formatting.
- **[structlog](https://www.structlog.org/)** — Structured logging.

## How it ties with the rest of the project

- **[main.py](../../main.py)** — `ingest-metrobus-gtfs-static` CLI command calls `gtfs_static.run(settings)`.
- **[infra/modules/cloudrun/main.tf](../../infra/modules/cloudrun/main.tf)** — Cloud Run Job `metrobus-gtfs-static` runs this command daily.
- **[infra/modules/scheduler/main.tf](../../infra/modules/scheduler/main.tf)** — Cloud Scheduler job `metrobus-gtfs-static-daily` triggers at 04:00 Mexico City time.
- **[infra/modules/bigquery/main.tf](../../infra/modules/bigquery/main.tf)** — Six external tables (`metrobus_stops`, `metrobus_routes`, etc.) read from the CSV paths written here.
- **[dbt_bigquery/models/staging/stg_metrobus_stops.sql](../../dbt_bigquery/models/staging/stg_metrobus_stops.sql)**, **[stg_metrobus_routes.sql](../../dbt_bigquery/models/staging/stg_metrobus_routes.sql)** — Staging models that clean the raw CSVs.
- **[.github/workflows/ci.yml](../../.github/workflows/ci.yml)** — `ingest-metrobus-static` CI job also runs this ingestor on every push to `main`.
- **[tests/ingestion/metrobus/test_gtfs_static.py](../../tests/ingestion/metrobus/test_gtfs_static.py)** — Unit tests for `run()`, `_find_zip_resource()`, validation, and path generation.
