# dbt_bigquery/models/staging/stg_metrobus_vehicle_positions.sql

## What it does

Flattens the GTFS-RT vehicle positions NDJSON data into a typed, relational table. The raw external table stores each vehicle entity's full protobuf payload serialized as a JSON string in the `vehicle` column. This model extracts the nested fields into top-level columns.

### Key transformations

- **`json_value(vehicle, '$.path')`** — Extracts string fields from the JSON `vehicle` column.
- **`safe_cast(json_value(...) as float64)`** — Safely casts numeric fields (lat, lon, bearing, speed); returns `NULL` instead of raising on bad values.
- Rows where `vehicle IS NULL` are filtered out.

### Output schema

| Column | Type | Source JSON path | Description |
|---|---|---|---|
| `entity_id` | STRING | `id` (top-level) | GTFS-RT FeedEntity identifier |
| `vehicle_id` | STRING | `$.vehicle.id` | Vehicle identifier |
| `vehicle_label` | STRING | `$.vehicle.label` | Human-readable vehicle label |
| `route_id` | STRING | `$.trip.route_id` | Route the vehicle is serving |
| `trip_id` | STRING | `$.trip.trip_id` | Active trip identifier |
| `latitude` | FLOAT64 | `$.position.latitude` | Vehicle latitude |
| `longitude` | FLOAT64 | `$.position.longitude` | Vehicle longitude |
| `bearing_deg` | FLOAT64 | `$.position.bearing` | Heading in degrees |
| `speed_ms` | FLOAT64 | `$.position.speed` | Speed in m/s |
| `current_status` | STRING | `$.current_status` | GTFS-RT stop status enum |
| `snapshot_at` | TIMESTAMP | `_snapshot_ts` | UTC poll timestamp |
| `ingestion_date` | DATE | `ingestion_date` | Hive partition key |

### Materialization

`view` in dataset `staging_cdmx`.

## Tools used

- **BigQuery SQL** — `json_value`, `safe_cast`, `where` filter.
- **dbt** — `{{ source() }}` macro referencing `raw_cdmx.metrobus_vehicle_positions`.

## How it ties with the rest of the project

- **Source:** [`raw_cdmx.metrobus_vehicle_positions`](sources.yml) — NDJSON external table with a `JSON`-typed `vehicle` column.
- **Downstream:** [`mart_metrobus_vehicle_positions_hourly.sql`](../marts/mart_metrobus_vehicle_positions_hourly.sql) — truncates `snapshot_at` to hourly, computes average position and speed per vehicle/route/hour.
- **Ingestor:** [`ingestion/metrobus/gtfs_rt.py`](../../../ingestion/metrobus/gtfs_rt.py) — writes `vp_{epoch_ms}.ndjson` files; `_parse_to_ndjson()` with `preserving_proto_field_name=True` produces the snake_case JSON paths extracted here.
