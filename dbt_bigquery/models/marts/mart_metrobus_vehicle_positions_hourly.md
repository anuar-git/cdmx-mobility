# dbt_bigquery/models/marts/mart_metrobus_vehicle_positions_hourly.sql

## What it does

Aggregates the 30-second GTFS-RT vehicle position snapshots (~2,880 per day) into an hourly fact table for Tableau analytics. Each row represents one vehicle's average position and speed on one route during one hour.

### Transformation

1. Reads from `stg_metrobus_vehicle_positions` (individual 30-second snapshots).
2. Truncates `snapshot_at` to hour with `TIMESTAMP_TRUNC(snapshot_at, HOUR)`.
3. Groups by `hour`, `route_id`, `vehicle_id`.
4. Computes:
   - `avg_latitude`, `avg_longitude` — centroid of all positions in the hour.
   - `avg_speed_ms` — average speed in m/s across snapshots.
   - `snapshot_count` — number of 30-second polls captured.
5. Filters out rows where `route_id` or `vehicle_id` is NULL.

### Explicit configuration

```sql
{{ config(
    materialized="table",
    partition_by={"field": "hour", "data_type": "timestamp", "granularity": "hour"},
    cluster_by=["route_id"],
) }}
```

- **Partition by `hour`** (TIMESTAMP, hourly granularity) — Tableau date-range filters prune to relevant partitions, reducing query cost.
- **Cluster by `route_id`** — Tableau route-level filters hit only relevant cluster blocks.

### Output schema

| Column | Type | Description |
|---|---|---|
| `hour` | TIMESTAMP | UTC hour (truncated to hour boundary) |
| `route_id` | STRING | Route identifier (clustering key) |
| `vehicle_id` | STRING | Vehicle identifier |
| `avg_latitude` | FLOAT64 | Average latitude across snapshots in the hour |
| `avg_longitude` | FLOAT64 | Average longitude across snapshots |
| `avg_speed_ms` | FLOAT64 | Average speed in m/s |
| `snapshot_count` | INTEGER | Number of 30-second polls aggregated |

### Materialization

`table` in dataset `marts_cdmx`, partitioned by `hour`, clustered by `route_id`.

## Tools used

- **BigQuery SQL** — `TIMESTAMP_TRUNC`, `AVG`, `COUNT`, `GROUP BY`.
- **dbt** — `{{ config() }}` for partition/cluster settings; `{{ ref() }}` macro.

## How it ties with the rest of the project

- **Upstream:** [`stg_metrobus_vehicle_positions`](../staging/stg_metrobus_vehicle_positions.sql) — flattened GTFS-RT snapshots.
- **Ingestor chain:** [`ingestion/metrobus/gtfs_rt.py`](../../../ingestion/metrobus/gtfs_rt.py) → GCS NDJSON → `raw_cdmx.metrobus_vehicle_positions` → `stg_metrobus_vehicle_positions` → this mart.
- **Join potential:** `route_id` links to [`stg_metrobus_routes`](../staging/stg_metrobus_routes.sql) for route name and colour lookups.
- **Consumers:** Tableau dashboard for Metrobús operational performance — speed heatmaps, route coverage, headway analysis.

> **Status:** The GTFS-RT daemon Cloud Run Service is not yet deployed. This mart will remain empty until `metrobus_gtfs_rt_vehicle_positions_url` is set and the service is applied via Terraform.
