# tests/ingestion/test_bq_logger.py

## What it tests

Unit tests for [`ingestion/bq_logger.py`](../../ingestion/bq_logger.py) — the `RunResult` dataclass and the `IngestionLogger` class that writes ingestion metrics to BigQuery.

## Test categories

### `RunResult` defaults

- `test_run_result_default_status` — Status defaults to `"success"`.
- `test_run_result_default_error_message_is_none` — `error_message` defaults to `None`.
- `test_run_result_default_row_count_is_none` — `row_count` defaults to `None`.
- `test_run_result_run_id_is_valid_uuid` — `run_id` is a well-formed UUID4 string.
- `test_run_result_run_ids_are_unique` — Two separate `RunResult` instances have different `run_id` values.

### `IngestionLogger.log`

- `test_log_calls_insert_rows_json` — Verifies `bigquery.Client.insert_rows_json()` is called exactly once.
- `test_log_passes_correct_table` — Table argument is `"{project}.meta_cdmx.ingestion_log"`.
- `test_log_row_contains_required_fields` — Row dict has correct `source`, `status`, `file_count`, `byte_count`, `row_count`, `error_message`, `run_id` values.
- `test_log_does_not_raise_on_row_errors` — A non-empty error list from `insert_rows_json` does not propagate.
- `test_log_does_not_raise_on_api_exception` — A `google.api_core.exceptions.NotFound` (table missing pre-Terraform) does not propagate.
- `test_log_error_result` — Error status and message are recorded correctly in the row.

## Testing approach

Uses `unittest.mock.patch("google.cloud.bigquery.Client")` to avoid real GCP calls. `MagicMock` controls `insert_rows_json` return values and side effects.

## Tools used

- **pytest** — Test runner.
- **`unittest.mock`** — `patch`, `MagicMock` for GCP client mocking.
- **`google.api_core.exceptions.NotFound`** — Tests the pre-Terraform resilience path.
