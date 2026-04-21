# tests/ingestion/metrobus/test_gtfs_rt.py

## What it tests

Unit tests for [`ingestion/metrobus/gtfs_rt.py`](../../../ingestion/metrobus/gtfs_rt.py) — the `_parse_to_ndjson()` pure converter, the `_fetch_protobuf()` retry function, and the `run()` daemon loop.

## Tests

### `_parse_to_ndjson()`

- `test_parse_to_ndjson_one_line_per_entity` — Output has exactly one JSON line per `FeedEntity`.
- `test_parse_to_ndjson_adds_snapshot_ts` — Every JSON record includes `"_snapshot_ts"` with the passed timestamp.
- `test_parse_to_ndjson_empty_feed` — An empty feed produces `b""`.
- `test_parse_to_ndjson_includes_entity_id_and_vehicle` — Records include `"id"` and `"vehicle"` keys.
- `test_parse_to_ndjson_uses_snake_case_field_names` — `MessageToDict(preserving_proto_field_name=True)` produces snake_case keys like `current_status`.

### `_fetch_protobuf()`

- `test_fetch_protobuf_retries_and_reraises` — With `max_retries=3`, the function attempts exactly 3 times before raising `httpx.NetworkError`.
- `test_fetch_protobuf_succeeds_on_second_attempt` — Recovers from a transient first-attempt failure and returns bytes on the second attempt.

### `run()` daemon loop

Tests use `monkeypatch.setattr("time.sleep", ...)` to inject a `StopIteration` at the right poll count — controlling how many iterations the infinite loop runs.

- `test_run_uploads_pb_and_ndjson` — One iteration produces exactly 2 uploads: one `vehicle_positions_raw/*.pb` and one `vehicle_positions/*.ndjson`.
- `test_run_uses_date_partition` — Both GCS paths contain `ingestion_date=`.
- `test_run_continues_after_http_error` — Poll 1 raises `RuntimeError`; poll 2 succeeds. Total uploads = 2 (only from poll 2). Verifies the daemon swallows per-poll exceptions.
- `test_run_logs_success_to_bq` — Success `RunResult` has `source="metrobus_gtfs_rt"`, `status="success"`, `file_count=2`, `row_count` equal to entity count.
- `test_run_logs_error_to_bq` — Error `RunResult` has `status="error"` and correct `error_message`.
- `test_run_calls_start_health_server` — `_start_health_server()` is called exactly once at daemon startup.
- `test_run_pb_uses_octet_stream_content_type` — The `.pb` upload uses `content_type="application/octet-stream"`.

## Testing approach

`_make_feed()` and `_make_feed_bytes()` helpers construct real `gtfs_realtime_pb2.FeedMessage` proto objects with synthetic vehicle entities, then serialize them. This tests the actual protobuf parsing path without a live endpoint.

`_fetch_protobuf`, `_start_health_server`, `GCSUploader`, and `IngestionLogger` are all patched. `time.sleep` is patched via `monkeypatch` to control the loop.

## Tools used

- **pytest** — Test runner with `monkeypatch`.
- **`gtfs_realtime_pb2`** — Constructs real protobuf FeedMessage objects for round-trip testing.
- **`json`** — Parses NDJSON output lines for field assertions.
- **`unittest.mock`** — `patch`, `MagicMock`.
- **httpx** — `httpx.NetworkError` used in retry tests.
