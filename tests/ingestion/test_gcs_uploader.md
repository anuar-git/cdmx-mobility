# tests/ingestion/test_gcs_uploader.py

## What it tests

Unit tests for [`ingestion/gcs_uploader.py`](../../ingestion/gcs_uploader.py) — the `GCSUploader` GCS write primitive.

## Tests

- `test_upload_returns_correct_gcs_uri` — `upload()` returns a correctly formatted `gs://{bucket}/{path}` URI.
- `test_upload_uses_correct_gcs_path` — `bucket.blob()` is called with the exact GCS path string passed to `upload()`.

Both tests also verify that `blob.upload_from_string()` is called with the correct bytes and `content_type`.

## Testing approach

`patch("google.cloud.storage.Client")` intercepts the GCS client constructor. Mock chain: `storage.Client()` → `.bucket()` → `.blob()` → `.upload_from_string()`. The mock bucket's `.name` attribute is set to verify the URI construction.

## Tools used

- **pytest** — Test runner.
- **`unittest.mock`** — `patch`, `MagicMock`.
