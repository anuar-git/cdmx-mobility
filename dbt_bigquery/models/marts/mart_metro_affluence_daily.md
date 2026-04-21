# dbt_bigquery/models/marts/mart_metro_affluence_daily.sql

## What it does

Aggregates Metro CDMX station entry counts into a daily fact table — one row per station/line/date. This is the final analytics layer consumed by Tableau dashboards for ridership analysis.

### Transformation

Groups `stg_metro_affluence` by `date`, `line`, and `station`, summing all `entries`. The `SUM` handles the rare case where a station appears multiple times for the same date in the raw data (e.g., multiple ingest runs for the same day).

### Output schema

| Column | Type | Description |
|---|---|---|
| `date` | DATE | Date of the recorded entries |
| `line` | STRING | Metro line name |
| `station` | STRING | Station name |
| `total_entries` | INTEGER | Total entry count for that station on that date |

### Materialization

`table` in dataset `marts_cdmx` (as defined in [dbt_project.yml](../../dbt_project.yml)). No explicit partition or cluster configured — the table is relatively small (one row per station/line/day).

## Tools used

- **BigQuery SQL** — `SUM()`, `GROUP BY`.
- **dbt** — `{{ ref('stg_metro_affluence') }}` macro.

## How it ties with the rest of the project

- **Upstream:** [`stg_metro_affluence`](../staging/stg_metro_affluence.sql) — staging view that cleans the raw CSV data.
- **Ingestor chain:** [`ingestion/metro/affluence.py`](../../../ingestion/metro/affluence.py) → GCS → `raw_cdmx.metro_affluence` (external table) → `stg_metro_affluence` (view) → this mart (table).
- **Consumers:** Tableau dashboard for Metro ridership trends (reads from `marts_cdmx`).
