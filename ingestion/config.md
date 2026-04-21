# ingestion/config.py

## What it does

Defines the `Settings` class — a single Pydantic v2 `BaseSettings` model that consolidates all runtime configuration for every ingestor. Settings are read from environment variables with the `CDMX_` prefix, with sensible defaults for non-secret values. An optional `.env` file is also supported.

All four ingestors (`affluence`, `gbfs`, `gtfs_static`, `gtfs_rt`) instantiate `Settings()` at startup. The settings object is then passed into the relevant `run()` function, making all configuration explicit and testable.

## Settings reference

| Field | Env var | Default | Purpose |
|---|---|---|---|
| `gcp_project_id` | `CDMX_GCP_PROJECT_ID` | **required** | GCP project ID for GCS and BigQuery |
| `raw_bucket_name` | `CDMX_RAW_BUCKET_NAME` | `cdmx-mobility-raw` | GCS bucket for raw landings |
| `metro_ckan_base_url` | `CDMX_METRO_CKAN_BASE_URL` | `https://datos.cdmx.gob.mx/api/3/action` | CKAN API base URL (shared by metro and Metrobús) |
| `metro_affluence_dataset_id` | `CDMX_METRO_AFFLUENCE_DATASET_ID` | `afluencia-diaria-del-metro-cdmx` | CKAN dataset slug for metro entry counts |
| `http_timeout_seconds` | `CDMX_HTTP_TIMEOUT_SECONDS` | `30` | HTTP client timeout (all ingestors) |
| `http_max_retries` | `CDMX_HTTP_MAX_RETRIES` | `3` | Max retry attempts (all ingestors) |
| `ecobici_gbfs_base_url` | `CDMX_ECOBICI_GBFS_BASE_URL` | `https://gbfs.mex.lyftbikes.com/gbfs/es` | GBFS feed root URL |
| `ecobici_api_key` | `CDMX_ECOBICI_API_KEY` | `""` | Optional Bearer token (feed is public) |
| `ecobici_poll_feeds` | `CDMX_ECOBICI_POLL_FEEDS` | `["station_information","station_status","system_alerts"]` | Which GBFS feeds to poll |
| `metrobus_gtfs_static_dataset_id` | `CDMX_METROBUS_GTFS_STATIC_DATASET_ID` | `gtfs` | CKAN dataset slug for SEMOVI unified CDMX GTFS |
| `metrobus_gtfs_rt_vehicle_positions_url` | `CDMX_METROBUS_GTFS_RT_VEHICLE_POSITIONS_URL` | `""` | GTFS-RT protobuf endpoint (obtain from SEMOVI) |
| `metrobus_gtfs_rt_poll_interval_seconds` | `CDMX_METROBUS_GTFS_RT_POLL_INTERVAL_SECONDS` | `30` | GTFS-RT daemon polling interval |

## Tools used

- **[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)** — `BaseSettings` with `env_prefix="CDMX_"` and optional `.env` file loading.

## How it ties with the rest of the project

- **[main.py](../main.py)** — Constructs `Settings()` once per CLI command and passes it to the `run()` function.
- **[ingestion/metro/affluence.py](metro/affluence.py)** — Uses `metro_ckan_base_url`, `metro_affluence_dataset_id`, `raw_bucket_name`, `gcp_project_id`.
- **[ingestion/ecobici/gbfs.py](ecobici/gbfs.py)** — Uses `ecobici_gbfs_base_url`, `ecobici_api_key`, `ecobici_poll_feeds`, `raw_bucket_name`, `gcp_project_id`.
- **[ingestion/metrobus/gtfs_static.py](metrobus/gtfs_static.py)** — Uses `metro_ckan_base_url`, `metrobus_gtfs_static_dataset_id`, `raw_bucket_name`, `gcp_project_id`.
- **[ingestion/metrobus/gtfs_rt.py](metrobus/gtfs_rt.py)** — Uses `metrobus_gtfs_rt_vehicle_positions_url`, `metrobus_gtfs_rt_poll_interval_seconds`, `raw_bucket_name`, `gcp_project_id`.
- **[infra/modules/cloudrun/main.tf](../infra/modules/cloudrun/main.tf)** — Sets `CDMX_`-prefixed env vars on Cloud Run resources, satisfying the required fields.
