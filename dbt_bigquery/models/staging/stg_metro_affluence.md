# dbt_bigquery/models/staging/stg_metro_affluence.sql

## What it does

Creates a staging view that cleans the raw metro affluence CSV data from the BigQuery external table. It is the first transformation layer between raw GCS files and downstream analytics.

### Transformations applied

| Raw column | Output column | Type cast | Transformation |
|---|---|---|---|
| `fecha` | `date` | `DATE` | `cast(fecha as date)` |
| `linea` | `line` | `STRING` | `trim()` |
| `estacion` | `station` | `STRING` | `trim()` |
| `afluencia` | `entries` | `INTEGER` | `cast(afluencia as integer)` |
| `ingestion_date` | `ingestion_date` | `DATE` | Passed through unchanged |

Rows where `afluencia IS NULL` are filtered out.

### Output schema

| Column | Type | Description |
|---|---|---|
| `date` | DATE | Date the entries were recorded |
| `line` | STRING | Metro line name (trimmed) |
| `station` | STRING | Station name (trimmed) |
| `entries` | INTEGER | Entry count for that station/date |
| `ingestion_date` | DATE | Hive partition — when the file was landed |

### Materialization

`view` in dataset `staging_cdmx` (as defined in [dbt_project.yml](../../dbt_project.yml)).

## Tools used

- **BigQuery SQL** — `cast()`, `trim()`, `where` filter.
- **dbt** — `{{ source() }}` macro references `raw_cdmx.metro_affluence`.

## How it ties with the rest of the project

- **Source:** [`raw_cdmx.metro_affluence`](sources.yml) — external table over `metro/affluence/ingestion_date=*/` GCS files.
- **Downstream:** [`mart_metro_affluence_daily.sql`](../marts/mart_metro_affluence_daily.sql) — groups by `date/line/station` and sums entries.
- **Ingestor:** [`ingestion/metro/affluence.py`](../../../ingestion/metro/affluence.py) — writes the CSV files that feed this view.
