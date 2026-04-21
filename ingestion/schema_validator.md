# ingestion/schema_validator.py

## What it does

Provides lightweight schema validation for all three data source types before any bytes are written to GCS. Validation is intentionally minimal — it only checks that required columns/keys are present, not their values. This catches malformed or renamed source data at ingest time rather than silently landing bad data.

### Constants

| Constant | Type | Used by |
|---|---|---|
| `GBFS_REQUIRED` | `frozenset[str]` | `validate_gbfs_envelope()` |
| `GTFS_STATIC_REQUIRED` | `dict[str, frozenset[str]]` | `validate_csv_header()` for GTFS feeds |
| `METRO_AFFLUENCE_REQUIRED` | `frozenset[str]` | `validate_csv_header()` for metro affluence CSVs |

### Functions

#### `validate_gbfs_envelope(payload, feed_name)`

Raises `ValueError` if the top-level GBFS JSON envelope is missing any of `last_updated`, `ttl`, or `data`.

#### `validate_csv_header(data, required_cols, source)`

Decodes only the first line of a CSV byte string and checks that all `required_cols` are present. Comparison is **case-insensitive** (`LINEA` and `linea` are both accepted). Only the header row is decoded — safe for large GTFS files like `stop_times.txt`.

### Required columns by feed

| Feed | Required columns |
|---|---|
| `stops` | `stop_id`, `stop_name`, `stop_lat`, `stop_lon` |
| `routes` | `route_id`, `route_short_name`, `route_type` |
| `trips` | `route_id`, `service_id`, `trip_id` |
| `stop_times` | `trip_id`, `stop_id`, `stop_sequence` |
| `calendar` | `service_id`, `monday`, `start_date`, `end_date` |
| `shapes` | `shape_id`, `shape_pt_lat`, `shape_pt_lon`, `shape_pt_sequence` |
| Metro affluence | `fecha`, `anio`, `mes`, `linea`, `estacion`, `afluencia` |

## Tools used

- **`csv`** — Standard library; `csv.reader` parses the header line cleanly including quoted fields.

## How it ties with the rest of the project

- **[ingestion/metro/affluence.py](metro/affluence.py)** — Calls `validate_csv_header(data, METRO_AFFLUENCE_REQUIRED, ...)` on each downloaded CSV before uploading.
- **[ingestion/ecobici/gbfs.py](ecobici/gbfs.py)** — Calls `validate_gbfs_envelope(payload, feed_name)` on the parsed JSON response.
- **[ingestion/metrobus/gtfs_static.py](metrobus/gtfs_static.py)** — Calls `validate_csv_header(data, GTFS_STATIC_REQUIRED[feed_name], ...)` for each GTFS feed extracted from the ZIP.
- **[tests/ingestion/test_schema_validator.py](../tests/ingestion/test_schema_validator.py)** — Unit tests for all validation paths including missing keys, case-insensitivity, and correct error messages.
