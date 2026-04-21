# ingestion/gbfs_client.py

## What it does

`GBFSClient` is an HTTP client for [GBFS (General Bikeshare Feed Specification)](https://gbfs.mobilitydata.org/) feeds. It fetches a single named feed (e.g., `station_status`, `station_information`, `system_alerts`) from the configured base URL and returns the parsed JSON payload as a Python dict.

The public `fetch(feed_name)` method delegates to `_fetch(feed_name)`, which is decorated with `@retry`:
- `stop_after_attempt(3)` — up to 3 total attempts.
- `wait_exponential(min=2, max=10)` — exponential backoff 2s → 10s.
- `reraise=True` — original exception propagates on exhaustion.

**Authentication:** if `api_key` is non-empty, an `Authorization: Bearer <api_key>` header is added. The EcoBici GBFS feed is currently public and does not require a key.

URL pattern: `{base_url}/{feed_name}.json`

## Tools used

- **[httpx](https://www.python-httpx.org/)** — Synchronous HTTP client with connection context manager.
- **[tenacity](https://tenacity.readthedocs.io/)** — Retry decorator with exponential backoff, matching the pattern used by `CKANClient`.

## How it ties with the rest of the project

- **[ingestion/ecobici/gbfs.py](ecobici/gbfs.py)** — Instantiates `GBFSClient` once per ingestor invocation and calls `fetch(feed_name)` for each feed in `settings.ecobici_poll_feeds`.
- **[ingestion/config.py](config.py)** — Provides `ecobici_gbfs_base_url`, `ecobici_api_key`, `http_timeout_seconds`, and `http_max_retries`.
- **[infra/modules/cloudrun/main.tf](../infra/modules/cloudrun/main.tf)** — Sets `CDMX_ECOBICI_GBFS_BASE_URL` env var on the Cloud Run Job for EcoBici.
- **[tests/ingestion/test_gbfs_client.py](../tests/ingestion/test_gbfs_client.py)** — Unit tests for fetch, HTTP error handling, and Bearer token injection.
