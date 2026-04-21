# dbt_bigquery/models/marts/mart_ecobici_availability_2min.sql

## What it does

Builds the primary EcoBici analytics fact table by joining 2-minute station status snapshots with the most recent daily station metadata. Each row represents one station's availability state at one 2-minute poll interval.

### Key design decisions

#### `latest_info` CTE

Station information is polled daily but status is polled every 2 minutes. A naïve join on `station_id` would cause a **fan-out** (each status row joining to all daily snapshots). The `latest_info` CTE uses `ROW_NUMBER() OVER (PARTITION BY station_id ORDER BY ingestion_date DESC)` to select only the most recent daily snapshot per station, ensuring a 1:1 join.

#### `availability_ratio`

Computed as `SAFE_DIVIDE(bikes_available, NULLIF(capacity, 0))`. `SAFE_DIVIDE` returns NULL on division by zero; `NULLIF(..., 0)` prevents divide-by-zero on stations with zero capacity.

### Output schema

| Column | Type | Description |
|---|---|---|
| `ingestion_ts` | STRING | 2-minute poll timestamp partition key |
| `feed_updated_at` | TIMESTAMP | When the GBFS feed was last updated |
| `station_id` | STRING | EcoBici station identifier |
| `station_name` | STRING | Full station name (from latest info) |
| `short_name` | STRING | Short public identifier |
| `lat` | FLOAT64 | Latitude |
| `lon` | FLOAT64 | Longitude |
| `capacity` | INTEGER | Total dock capacity |
| `bikes_available` | INTEGER | Available bikes at snapshot time |
| `docks_available` | INTEGER | Available docks at snapshot time |
| `bikes_disabled` | INTEGER | Disabled bikes |
| `docks_disabled` | INTEGER | Disabled docks |
| `is_renting` | BOOL | Station accepting rentals |
| `is_returning` | BOOL | Station accepting returns |
| `is_installed` | BOOL | Station installed |
| `station_last_reported_at` | TIMESTAMP | Last sensor report |
| `availability_ratio` | FLOAT64 | `bikes_available / capacity` (0–1) |

### Materialization

`table` in dataset `marts_cdmx`. Implicitly partitioned by `ingestion_ts` scan pattern (no explicit BigQuery partitioning configured — inherits the staging view's data distribution).

## Tools used

- **BigQuery SQL** — `ROW_NUMBER()`, `SAFE_DIVIDE`, `NULLIF`, `LEFT JOIN`.
- **dbt** — `{{ ref() }}` macros for both `stg_ecobici_station_status` and `stg_ecobici_station_information`.

## How it ties with the rest of the project

- **Upstream:** [`stg_ecobici_station_status`](../staging/stg_ecobici_station_status.sql) + [`stg_ecobici_station_information`](../staging/stg_ecobici_station_information.sql).
- **Ingestor chain:** [`ingestion/ecobici/gbfs.py`](../../../ingestion/ecobici/gbfs.py) → GCS → external tables → staging views → this mart.
- **Consumers:** Tableau dashboard for EcoBici dock availability and spatial distribution.
