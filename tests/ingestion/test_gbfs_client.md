# tests/ingestion/test_gbfs_client.py

## What it tests

Unit tests for [`ingestion/gbfs_client.py`](../../ingestion/gbfs_client.py) — the `GBFSClient` HTTP client for EcoBici GBFS feeds.

## Tests

- `test_fetch_returns_parsed_json` — `fetch()` returns the parsed JSON dict from a successful response.
- `test_fetch_raises_on_http_error` — `fetch()` propagates `httpx.HTTPStatusError` when the server returns a non-2xx response.
- `test_fetch_sends_bearer_token_when_api_key_set` — When `api_key` is non-empty, the request includes `Authorization: Bearer {api_key}` header.
- `test_fetch_sends_no_auth_header_when_no_api_key` — When `api_key` is empty string, `headers` passed to `httpx.Client.get()` is `{}`.

## Testing approach

All HTTP calls are mocked with `patch("httpx.Client")`. The `headers` kwarg is inspected via `call_args.kwargs` to verify auth header behavior.

## Tools used

- **pytest** — Test runner.
- **`unittest.mock`** — `patch`, `MagicMock`.
- **httpx** — `httpx.HTTPStatusError` used as the side effect in the error test.
