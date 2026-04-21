# tests/ingestion/test_schema_validator.py

## What it tests

Unit tests for [`ingestion/schema_validator.py`](../../ingestion/schema_validator.py) — the `validate_gbfs_envelope()` and `validate_csv_header()` functions, plus the `GBFS_REQUIRED`, `GTFS_STATIC_REQUIRED`, and `METRO_AFFLUENCE_REQUIRED` constants.

## Test categories

### `validate_gbfs_envelope`

- `test_validate_gbfs_envelope_passes_with_all_keys` — Valid GBFS envelope with all three required keys passes without error.
- `test_validate_gbfs_envelope_raises_on_missing_ttl` — Raises `ValueError` mentioning `"ttl"` when `ttl` is absent.
- `test_validate_gbfs_envelope_raises_on_missing_data` — Raises `ValueError` mentioning `"data"`.
- `test_validate_gbfs_envelope_error_names_feed` — Error message includes the feed name (`"station_information"`).

### `validate_csv_header`

- `test_validate_csv_header_passes_for_stops` — Valid stops CSV header passes.
- `test_validate_csv_header_passes_for_routes` — Valid routes CSV header passes.
- `test_validate_csv_header_raises_on_missing_stop_lat` — Missing `stop_lat` raises `ValueError` naming the missing column.
- `test_validate_csv_header_raises_on_missing_route_type` — Missing `route_type` raises correctly.
- `test_validate_csv_header_is_case_insensitive` — `STOP_ID`, `STOP_LAT` etc. are accepted (real-world GTFS files sometimes use uppercase).
- `test_validate_csv_header_metro_affluence_passes` — Valid metro affluence header passes.
- `test_validate_csv_header_metro_affluence_raises_on_missing` — Missing `estacion` raises `ValueError`.
- `test_validate_csv_header_error_names_source` — Error message includes the `source` argument string.
- `test_validate_csv_header_all_gtfs_feeds_have_required_keys` — Sanity check: every feed in `GTFS_STATIC_REQUIRED` has at least one required column.

## Tools used

- **pytest** — Test runner; `pytest.raises` with `match=` for error message assertion.
- No mocking needed — `schema_validator.py` has no I/O dependencies.
