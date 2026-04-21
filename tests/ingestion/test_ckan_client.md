# tests/ingestion/test_ckan_client.py

## What it tests

Unit tests for [`ingestion/ckan_client.py`](../../ingestion/ckan_client.py) — the `CKANClient` HTTP client for the `datos.cdmx.gob.mx` CKAN portal.

## Tests

- `test_get_resources_returns_list` — `get_resources()` returns the resource list from a successful CKAN `package_show` response.
- `test_get_resources_raises_on_ckan_error` — `get_resources()` raises `RuntimeError` when CKAN returns `"success": false` in the response body.
- `test_download_resource_returns_bytes` — `download_resource()` returns raw bytes from the HTTP response content.

## Testing approach

All HTTP calls are mocked with `patch("httpx.Client")` to intercept the context manager and return a controlled `MagicMock` response. No real network calls are made.

The retry decorator (`tenacity`) is transparent in tests because `max_retries=1` means only one attempt is made before propagation — no retry delay in tests.

## Tools used

- **pytest** — Test runner.
- **`unittest.mock`** — `patch`, `MagicMock` for httpx mocking.
