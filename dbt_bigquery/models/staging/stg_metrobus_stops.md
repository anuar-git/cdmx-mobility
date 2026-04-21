# dbt_bigquery/models/staging/stg_metrobus_stops.sql

## What it does

Cleans and types the raw GTFS `stops.txt` CSV data from the BigQuery external table. The raw CSV stores all values as strings; this model casts coordinates to floats and normalizes empty strings to NULL.

### Transformations applied

| Raw column | Output column | Type cast | Transformation |
|---|---|---|---|
| `stop_id` | `stop_id` | STRING | `trim()` |
| `stop_code` | `stop_code` | STRING | `nullif(trim(...), '')` |
| `stop_name` | `stop_name` | STRING | `trim()` |
| `stop_lat` | `latitude` | FLOAT64 | `cast(stop_lat as float64)` |
| `stop_lon` | `longitude` | FLOAT64 | `cast(stop_lon as float64)` |
| `location_type` | `location_type` | INTEGER | `coalesce(location_type, 0)` — defaults to `0` (stop) |
| `parent_station` | `parent_station` | STRING | `nullif(trim(coalesce(..., '')), '')` |
| `ingestion_date` | `ingestion_date` | DATE | Passed through |

Rows where `stop_id IS NULL` are filtered out.

### Output schema

| Column | Type | Description |
|---|---|---|
| `stop_id` | STRING | Unique stop identifier |
| `stop_code` | STRING | Short public code (nullable) |
| `stop_name` | STRING | Human-readable stop name |
| `latitude` | FLOAT64 | WGS-84 latitude |
| `longitude` | FLOAT64 | WGS-84 longitude |
| `location_type` | INTEGER | GTFS location type (0=stop, 1=station, 2=entrance) |
| `parent_station` | STRING | Parent station stop_id (nullable) |
| `ingestion_date` | DATE | Partition key |

### Materialization

`view` in dataset `staging_cdmx`.

## Tools used

- **BigQuery SQL** — `cast`, `trim`, `nullif`, `coalesce`.
- **dbt** — `{{ source() }}` macro.

## How it ties with the rest of the project

- **Source:** [`raw_cdmx.metrobus_stops`](sources.yml) — CSV external table partitioned by `ingestion_date`.
- **Ingestor:** [`ingestion/metrobus/gtfs_static.py`](../../../ingestion/metrobus/gtfs_static.py) — writes `stops.csv` from the SEMOVI unified GTFS ZIP.
- **Potential downstream:** Stop-level analytics, route geometry joins, service area dashboards.
