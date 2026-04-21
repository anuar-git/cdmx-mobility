# ingestion/ckan_client.py

## What it does

`CKANClient` is an HTTP client for the [CKAN](https://ckan.org/) open data portal at `datos.cdmx.gob.mx`. It provides two methods:

- **`get_resources(dataset_id)`** — Calls the CKAN `package_show` API to retrieve the list of resources (files) attached to a dataset. Raises `RuntimeError` if CKAN returns `"success": false`.
- **`download_resource(resource_url)`** — Downloads a resource file as raw bytes. Follows redirects.

Both public methods delegate to `@retry`-decorated private counterparts (`_get_resources`, `_download_resource`). The retry policy uses:
- `stop_after_attempt(3)` — up to 3 total attempts.
- `wait_exponential(min=2, max=10)` — 2s → 4s → 10s backoff.
- `reraise=True` — the original exception propagates after exhausted retries.

## Tools used

- **[httpx](https://www.python-httpx.org/)** — HTTP client. Used with a context manager to ensure connection cleanup. `follow_redirects=True` handles CDN redirects on CKAN resource downloads.
- **[tenacity](https://tenacity.readthedocs.io/)** — `@retry` decorator with exponential backoff.

## How it ties with the rest of the project

- **[ingestion/metro/affluence.py](metro/affluence.py)** — Instantiates `CKANClient` to fetch the metro affluence CSV resources from CKAN dataset `afluencia-diaria-del-metro-cdmx`.
- **[ingestion/metrobus/gtfs_static.py](metrobus/gtfs_static.py)** — Instantiates `CKANClient` to fetch the SEMOVI unified CDMX GTFS ZIP from CKAN dataset `gtfs`. Both ingestors share the same `metro_ckan_base_url` setting.
- **[ingestion/config.py](config.py)** — Provides `metro_ckan_base_url`, `http_timeout_seconds`, and `http_max_retries` used to construct the client.
- **[tests/ingestion/test_ckan_client.py](../tests/ingestion/test_ckan_client.py)** — Unit tests covering `get_resources`, `download_resource`, CKAN error handling, and retry behavior.
