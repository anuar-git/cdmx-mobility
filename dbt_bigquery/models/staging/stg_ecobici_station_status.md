# dbt_bigquery/models/staging/stg_ecobici_station_status.sql

## What it does

Explodes the GBFS `station_status` JSON feed into a flat, typed table. The raw external table stores each 2-minute snapshot as a single JSON blob in the `data` column; this model unnests the `$.stations` array so each row represents one station's status at one snapshot time.

### Key transformations

- **`json_query_array(data, '$.stations')`** + **`UNNEST`** — Explodes the nested stations array into individual rows.
- **`timestamp_seconds(last_updated)`** — Converts the GBFS Unix epoch to a BigQuery `TIMESTAMP`.
- **`json_value(station_el, '$.field')`** — Extracts each station field from the JSON element.
- **`cast(... as integer)`** — Typed bike/dock counts.
- **`json_value(...) = '1'`** — Converts string booleans to `BOOL` for `is_renting`, `is_returning`, `is_installed`.
- **`timestamp_seconds(cast(json_value(station_el, '$.last_reported') as integer))`** — Station-level last-reported timestamp.

### Output schema

| Column | Type | Description |
|---|---|---|
| `ingestion_ts` | STRING | Hive partition — UTC minute of snapshot |
| `feed_updated_at` | TIMESTAMP | When the feed was updated by the provider |
| `station_id` | STRING | EcoBici station identifier |
| `bikes_available` | INTEGER | Available bikes |
| `docks_available` | INTEGER | Available docks |
| `bikes_disabled` | INTEGER | Disabled bikes |
| `docks_disabled` | INTEGER | Disabled docks |
| `is_renting` | BOOL | Station accepting bike rentals |
| `is_returning` | BOOL | Station accepting returns |
| `is_installed` | BOOL | Station physically installed |
| `station_last_reported_at` | TIMESTAMP | Last sensor report from the station |

### Materialization

`view` in dataset `staging_cdmx`.

## Tools used

- **BigQuery SQL** — `json_query_array`, `unnest`, `json_value`, `timestamp_seconds`, `cast`.
- **dbt** — `{{ source() }}` macro.

## How it ties with the rest of the project

- **Source:** [`raw_cdmx.ecobici_station_status`](sources.yml) — NDJSON external table.
- **Downstream:** [`mart_ecobici_availability_2min.sql`](../marts/mart_ecobici_availability_2min.sql) — joins status with station information to compute availability ratios.
- **Ingestor:** [`ingestion/ecobici/gbfs.py`](../../../ingestion/ecobici/gbfs.py) — writes the `station_status.json` files.
