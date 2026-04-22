# infra/modules/bigquery/main.tf

## What it does

Provisions all BigQuery datasets and tables for the platform. This module is the bridge between raw GCS files (written by ingestors) and the SQL transformation layer (dbt).

## Datasets

Four datasets are created via a `for_each` loop over a `local.datasets` map:

| Dataset | Purpose | Table expiration |
|---|---|---|
| `raw_cdmx` | External tables over GCS raw files | None |
| `staging_cdmx` | dbt staging views | 7 days (auto-expire) |
| `marts_cdmx` | dbt mart tables (Tableau source) | None |
| `meta_cdmx` | Ingestion logs, pipeline metadata | None |

## External tables (in `raw_cdmx`)

### EcoBici (NDJSON)

| Table | GCS source | Partition |
|---|---|---|
| `ecobici_station_status` | `ecobici/station_status/*` | `ingestion_ts:STRING` |
| `ecobici_station_information` | `ecobici/station_information/*` | `ingestion_date:DATE` |
| `ecobici_system_alerts` | `ecobici/system_alerts/*` | `ingestion_ts:STRING` |

Schema: `last_updated INTEGER`, `ttl INTEGER`, `data JSON`. The `data` column is BigQuery native JSON — staging models use `json_query_array` + `unnest` to explode it.

### Metrobús static (CSV, `for_each`)

Six tables created from `local.metrobus_static_schemas`: `metrobus_stops`, `metrobus_routes`, `metrobus_trips`, `metrobus_stop_times`, `metrobus_calendar`, `metrobus_shapes`.

- Format: CSV, `skip_leading_rows = 1`.
- Partition: `ingestion_date:DATE`.
- Schemas are explicitly typed (IDs as STRING, lat/lon as FLOAT64, sequences as INTEGER) to avoid CSV auto-detection issues.

### Metrobús GTFS-RT (NDJSON)

`metrobus_vehicle_positions` — reads from `metrobus/vehicle_positions/*`, partition `ingestion_date:DATE`. The `vehicle` column is typed `JSON` to hold the full VehiclePosition protobuf payload.

## Native table (in `meta_cdmx`)

`ingestion_log` — DAY-partitioned on `ingested_at`. Receives one row per ingestor run from `IngestionLogger`. Schema: `source`, `run_id`, `file_count`, `byte_count`, `row_count`, `status`, `error_message`, `ingested_at`.

## How it ties with the rest of the project

- **[infra/modules/storage/main.tf](../storage/main.tf)** — GCS bucket name (`raw_bucket_name`) used in all `source_uris`.
- **[dbt_bigquery/models/staging/sources.yml](../../../dbt_bigquery/models/staging/sources.yml)** — dbt source definitions must match the table IDs, dataset (`raw_cdmx`), and partition column names declared here.
- **[ingestion/bq_logger.py](../../../ingestion/bq_logger.py)** — Writes to `meta_cdmx.ingestion_log`; this table must exist before the ingestors run (i.e., Terraform must be applied first).
- **[infra/main.tf](../../main.tf)** — Passes `project_id`, `location`, and `raw_bucket_name` from `module.storage`.
