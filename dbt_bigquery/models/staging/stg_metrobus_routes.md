# dbt_bigquery/models/staging/stg_metrobus_routes.sql

## What it does

Cleans and types the raw GTFS `routes.txt` CSV data. Trims whitespace, normalizes empty optional fields (agency, route colours) to NULL, and filters out rows without a `route_id`.

### Transformations applied

| Raw column | Output column | Transformation |
|---|---|---|
| `route_id` | `route_id` | `trim()` |
| `agency_id` | `agency_id` | `nullif(trim(coalesce(..., '')), '')` |
| `route_short_name` | `route_short_name` | `trim()` |
| `route_long_name` | `route_long_name` | `trim()` |
| `route_type` | `route_type` | Passed through |
| `route_color` | `route_color` | `nullif(trim(coalesce(..., '')), '')` |
| `route_text_color` | `route_text_color` | `nullif(trim(coalesce(..., '')), '')` |
| `ingestion_date` | `ingestion_date` | Passed through |

Rows where `route_id IS NULL` are filtered out.

### Output schema

| Column | Type | Description |
|---|---|---|
| `route_id` | STRING | Unique route identifier |
| `agency_id` | STRING | Transit agency (nullable — mixed operators in SEMOVI ZIP) |
| `route_short_name` | STRING | Short public route name |
| `route_long_name` | STRING | Full route description |
| `route_type` | INTEGER | GTFS mode (3=bus, 5=cable car, etc.) |
| `route_color` | STRING | Hex colour for map rendering (nullable) |
| `route_text_color` | STRING | Hex colour for text on route colour (nullable) |
| `ingestion_date` | DATE | Partition key |

### Materialization

`view` in dataset `staging_cdmx`.

## Tools used

- **BigQuery SQL** — `trim`, `nullif`, `coalesce`.
- **dbt** — `{{ source() }}` macro.

## How it ties with the rest of the project

- **Source:** [`raw_cdmx.metrobus_routes`](sources.yml) — CSV external table.
- **Ingestor:** [`ingestion/metrobus/gtfs_static.py`](../../../ingestion/metrobus/gtfs_static.py) — writes `routes.csv`.
- **Downstream:** `route_id` is the clustering key in [`mart_metrobus_vehicle_positions_hourly.sql`](../marts/mart_metrobus_vehicle_positions_hourly.sql) for Tableau route-level filtering.
