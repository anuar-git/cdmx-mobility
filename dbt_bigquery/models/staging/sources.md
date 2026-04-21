# dbt_bigquery/models/staging/sources.yml

## What it does

Declares all external raw data sources that dbt staging models read from. Each source entry maps to a BigQuery external table (backed by GCS files) in the `raw_cdmx` dataset of the `cdmx-mobility-prod` project.

This file is the **contract** between the ingestion layer and the transformation layer: if an ingestor changes the GCS path structure, the corresponding external table definition in Terraform and the source entry here must both be updated.

## Sources declared

### `raw_cdmx.metro_affluence`

- **GCS path:** `metro/affluence/ingestion_date=YYYY-MM-DD/*.csv`
- **Format:** CSV
- **Partition:** `ingestion_date` (Hive-style DATE)
- **Key columns:** `fecha`, `linea`, `estacion`, `afluencia`

### `raw_cdmx.ecobici_station_status`

- **GCS path:** `ecobici/station_status/ingestion_ts=YYYY-MM-DDTHH-MM/*.json`
- **Format:** NDJSON (native BigQuery JSON column `data`)
- **Partition:** `ingestion_ts` (STRING, per minute)
- **Key columns:** `last_updated`, `ttl`, `data` (contains nested `stations` array)

### `raw_cdmx.ecobici_station_information`

- **GCS path:** `ecobici/station_information/ingestion_date=YYYY-MM-DD/*.json`
- **Format:** NDJSON
- **Partition:** `ingestion_date` (DATE, daily)
- **Key columns:** `last_updated`, `ttl`, `data`

### `raw_cdmx.ecobici_system_alerts`

- **GCS path:** `ecobici/system_alerts/ingestion_ts=YYYY-MM-DDTHH-MM/*.json`
- **Format:** NDJSON
- **Partition:** `ingestion_ts` (STRING, per minute)

### `raw_cdmx.metrobus_stops` / `metrobus_routes` / `metrobus_trips` / `metrobus_stop_times` / `metrobus_calendar` / `metrobus_shapes`

- **GCS path:** `metrobus/static/{feed}/ingestion_date=YYYY-MM-DD/*.csv`
- **Format:** CSV (standard GTFS)
- **Partition:** `ingestion_date` (DATE, daily)

### `raw_cdmx.metrobus_vehicle_positions`

- **GCS path:** `metrobus/vehicle_positions/ingestion_date=YYYY-MM-DD/*.ndjson`
- **Format:** NDJSON
- **Partition:** `ingestion_date` (DATE)
- **Key columns:** `id` (FeedEntity ID), `vehicle` (full VehiclePosition proto as JSON), `_snapshot_ts`

## How it ties with the rest of the project

- **[infra/modules/bigquery/main.tf](../../../infra/modules/bigquery/main.tf)** — Provisions every external table listed here. The GCS paths, formats, and partition column names must match.
- **[ingestion/](../../../ingestion/)** — Ingestors write files to the GCS paths declared as sources.
- **[stg_metro_affluence.sql](stg_metro_affluence.sql)**, **[stg_ecobici_station_status.sql](stg_ecobici_station_status.sql)**, etc. — Reference these sources via `{{ source('raw_cdmx', 'table_name') }}`.
- **[dbt_bigquery/dbt_project.yml](../../dbt_project.yml)** — `profile: cdmx_mobility` determines which BigQuery project/dataset connection is used.
