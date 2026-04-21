# tests/ingestion/ecobici/test_gbfs.py

## What it tests

Integration-style unit tests for [`ingestion/ecobici/gbfs.py`](../../../ingestion/ecobici/gbfs.py) — the `run()` function for the EcoBici GBFS ingestor.

## Tests

### Upload and feed routing

- `test_run_uploads_all_feeds` — `run()` calls `GBFSClient.fetch()` and `GCSUploader.upload()` exactly 3 times (once per feed in the default feed list), and all uploads use `content_type="application/json"`.

### GCS path partitioning

- `test_run_station_information_uses_date_partition` — `station_information` (static feed) uses `ingestion_date=` in the GCS path, not `ingestion_ts=`.
- `test_run_station_status_uses_ts_partition` — `station_status` (dynamic feed) uses `ingestion_ts=`, not `ingestion_date=`.
- `test_run_system_alerts_uses_ts_partition` — `system_alerts` uses `ingestion_ts=`.

### Configuration

- `test_run_passes_api_key_to_client` — The `api_key` from settings is forwarded to `GBFSClient`.

### Validation and error handling

- `test_run_raises_on_invalid_gbfs_envelope` — When the fetched payload is missing `ttl` and `data`, a `ValueError` is raised and `upload()` is never called.
- `test_run_logs_error_on_fetch_failure` — When `GBFSClient.fetch()` raises `RuntimeError`, the `RunResult` logged to BigQuery has `status="error"` and the error message captured.

### Observability

- `test_run_logs_success_with_station_count` — Logged `RunResult` has `status="success"`, `row_count` equal to the station count, and `file_count=1`.

## Testing approach

Uses `Settings.model_construct()` to bypass env-var validation and construct settings directly. All I/O dependencies (`GBFSClient`, `GCSUploader`, `IngestionLogger`) are patched at the module level. No network or GCS calls are made.

## Tools used

- **pytest** — Test runner.
- **`unittest.mock.patch`** — Patches `GBFSClient`, `GCSUploader`, `IngestionLogger`.
