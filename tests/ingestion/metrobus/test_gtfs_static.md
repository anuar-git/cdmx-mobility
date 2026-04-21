# tests/ingestion/metrobus/test_gtfs_static.py

## What it tests

Unit tests for [`ingestion/metrobus/gtfs_static.py`](../../../ingestion/metrobus/gtfs_static.py) — the `_find_zip_resource()` helper and the `run()` function for the Metrobús GTFS static ingestor.

## Tests

### `_find_zip_resource()`

- `test_find_zip_resource_by_format` — Returns the resource with `format == "ZIP"` from a mixed resource list.
- `test_find_zip_resource_by_url_extension` — Matches resources whose URL ends in `.zip` even when format is empty.
- `test_find_zip_resource_raises_if_none` — Raises `RuntimeError` with message `"No ZIP resource found"` when no ZIP candidates exist.
- `test_find_zip_resource_picks_most_recent` — Returns the resource with the latest `last_modified` date when multiple ZIPs are present.
- `test_find_zip_resource_accepts_gtfs_format` — `format == "GTFS"` is also accepted as a ZIP candidate.

### `run()`

- `test_run_uploads_all_expected_feeds` — Six uploads occur (one per expected GTFS feed).
- `test_run_skips_unexpected_zip_entries` — `agency.txt`, `feed_info.txt`, `frequencies.txt` inside the ZIP are skipped; still exactly 6 uploads.
- `test_run_uses_date_partition` — GCS path for `stops` contains `ingestion_date=` and ends with `stops.csv`.
- `test_run_uses_text_csv_content_type` — All uploads use `content_type="text/csv"`.
- `test_run_raises_if_no_zip_resource` — Non-ZIP CKAN resources raise `RuntimeError`.
- `test_run_passes_correct_ckan_dataset_id` — `get_resources()` is called with the dataset ID from settings.
- `test_run_raises_on_invalid_csv_header` — A `stops.txt` with wrong headers raises `ValueError` naming the missing column; `upload()` is not called.
- `test_run_logs_metrics_to_bq` — Logged `RunResult` has `source="metrobus_gtfs_static"`, `status="success"`, `file_count=6`, and non-zero `byte_count`.

## Testing approach

A `_make_gtfs_zip()` helper constructs real in-memory ZIP files with correct CSV headers for each feed. Uses `Settings.model_construct()` to bypass env-var validation. All I/O is patched (`CKANClient`, `GCSUploader`, `IngestionLogger`).

## Tools used

- **pytest** — Test runner with `pytest.raises`.
- **`zipfile`** + **`io.BytesIO`** — Constructs real ZIP bytes for testing.
- **`unittest.mock.patch`** — Patches all I/O dependencies.
