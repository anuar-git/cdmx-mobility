# dbt_bigquery/models/staging/stg_ecobici_station_information.sql

## What it does

Explodes the GBFS `station_information` feed JSON into a flat, typed table of station metadata. Unlike `station_status`, this feed is relatively static (polled once per day) and contains geographic and descriptive attributes — name, coordinates, capacity.

### Key transformations

- **`json_query_array(data, '$.stations')`** + **`UNNEST`** — Explodes the nested stations array.
- **`json_value(station_el, '$.field')`** — Extracts each metadata field from the JSON element.
- **`cast(... as float64)`** — Typed lat/lon coordinates.
- **`cast(... as integer)`** — Station capacity.

### Output schema

| Column | Type | Description |
|---|---|---|
| `ingestion_date` | DATE | Hive partition — when the file was landed |
| `station_id` | STRING | EcoBici station identifier |
| `name` | STRING | Full station name |
| `short_name` | STRING | Short public identifier |
| `lat` | FLOAT64 | WGS-84 latitude |
| `lon` | FLOAT64 | WGS-84 longitude |
| `capacity` | INTEGER | Total dock capacity |

### Materialization

`view` in dataset `staging_cdmx`.

## Tools used

- **BigQuery SQL** — `json_query_array`, `unnest`, `json_value`, `cast`.
- **dbt** — `{{ source() }}` macro.

## How it ties with the rest of the project

- **Source:** [`raw_cdmx.ecobici_station_information`](sources.yml) — NDJSON external table, daily partition.
- **Downstream:** [`mart_ecobici_availability_2min.sql`](../marts/mart_ecobici_availability_2min.sql) — joins with station status; uses `capacity` to compute `availability_ratio`. Uses `latest_info` CTE (most recent daily snapshot per station) to avoid fan-out.
- **Ingestor:** [`ingestion/ecobici/gbfs.py`](../../../ingestion/ecobici/gbfs.py) — writes `station_information.json` once per day to `ecobici/station_information/ingestion_date=YYYY-MM-DD/`.
