# ingestion/metro/affluence.py

## What it does

Ingests Mexico City Metro entry count data from the CKAN open data portal and lands it in GCS. This is a **one-shot batch job** — it runs to completion and exits.

### Execution flow (`run(settings)`)

1. Initializes `IngestionLogger` and a `RunResult(source="metro_affluence")`.
2. Creates a `CKANClient` using the CKAN base URL and HTTP settings from `Settings`.
3. Creates a `GCSUploader` pointing at the configured raw bucket.
4. Calls `client.get_resources(metro_affluence_dataset_id)` to get the resource list.
5. Filters to CSV resources, excluding any resource whose name contains `"diccionario"` (data dictionary files).
6. For each CSV resource:
   - Downloads the bytes via `client.download_resource(url)`.
   - Validates the CSV header against `METRO_AFFLUENCE_REQUIRED` (`fecha`, `anio`, `mes`, `linea`, `estacion`, `afluencia`).
   - Uploads to `metro/affluence/ingestion_date=YYYY-MM-DD/{filename}`.
   - Accumulates `file_count`, `byte_count`, `row_count` in `RunResult`.
7. On any exception: sets `result.status = "error"` and re-raises.
8. In the `finally` block: logs the `RunResult` to BigQuery unconditionally.

### GCS path pattern

```
metro/affluence/ingestion_date=YYYY-MM-DD/{original_filename}.csv
```

Partitioned by `ingestion_date` (today's date at run time).

## Tools used

- **[ingestion/ckan_client.py](../ckan_client.py)** — Downloads resources from `datos.cdmx.gob.mx`.
- **[ingestion/gcs_uploader.py](../gcs_uploader.py)** — Writes CSV bytes to GCS.
- **[ingestion/schema_validator.py](../schema_validator.py)** — Validates CSV header before upload.
- **[ingestion/bq_logger.py](../bq_logger.py)** — Records run metrics to `meta_cdmx.ingestion_log`.
- **[structlog](https://www.structlog.org/)** — Structured logging for download/upload events.
- **`datetime`** — Standard library; provides today's date for the Hive partition key.

## How it ties with the rest of the project

- **[main.py](../../main.py)** — The `ingest-metro-affluence` CLI command calls `affluence.run(settings)`.
- **[infra/modules/storage/main.tf](../../infra/modules/storage/main.tf)** — The `metro/` prefix in GCS has a lifecycle rule: move to COLDLINE after 90 days.
- **[infra/modules/bigquery/main.tf](../../infra/modules/bigquery/main.tf)** — The external table `raw_cdmx.metro_affluence` points to `metro/affluence/ingestion_date=*/*.csv` (partitioned by `ingestion_date`).
- **[dbt_bigquery/models/staging/stg_metro_affluence.sql](../../dbt_bigquery/models/staging/stg_metro_affluence.sql)** — Reads from the external table and casts/cleans the raw columns.
- **[.github/workflows/ci.yml](../../.github/workflows/ci.yml)** — The `ingest-metro` CI job runs this ingestor on every push to `main`.
- **[tests/ingestion/ecobici/test_gbfs.py](../../tests/ingestion/ecobici/test_gbfs.py)** — *(No direct test for affluence; covered via integration CI run.)*
