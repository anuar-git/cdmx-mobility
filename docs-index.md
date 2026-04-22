# Documentation Index

This index lists every source file in the project and links to its corresponding documentation file.

## Root

| File | Documentation |
|---|---|
| [main.py](main.py) | [main.md](main.md) |
| [pyproject.toml](pyproject.toml) | [pyproject.md](pyproject.md) |
| [Dockerfile](Dockerfile) | [Dockerfile.md](Dockerfile.md) |
| [Makefile](Makefile) | [Makefile.md](Makefile.md) |
| [.pre-commit-config.yaml](.pre-commit-config.yaml) | [pre-commit-config.md](pre-commit-config.md) |
| [.sqlfluff](.sqlfluff) | [sqlfluff.md](sqlfluff.md) |

## CI/CD

| File | Documentation |
|---|---|
| [.github/workflows/ci.yml](.github/workflows/ci.yml) | [.github/workflows/ci.md](.github/workflows/ci.md) |

## Ingestion layer

| File | Documentation |
|---|---|
| [ingestion/config.py](ingestion/config.py) | [ingestion/config.md](ingestion/config.md) |
| [ingestion/bq_logger.py](ingestion/bq_logger.py) | [ingestion/bq_logger.md](ingestion/bq_logger.md) |
| [ingestion/ckan_client.py](ingestion/ckan_client.py) | [ingestion/ckan_client.md](ingestion/ckan_client.md) |
| [ingestion/gbfs_client.py](ingestion/gbfs_client.py) | [ingestion/gbfs_client.md](ingestion/gbfs_client.md) |
| [ingestion/gcs_uploader.py](ingestion/gcs_uploader.py) | [ingestion/gcs_uploader.md](ingestion/gcs_uploader.md) |
| [ingestion/schema_validator.py](ingestion/schema_validator.py) | [ingestion/schema_validator.md](ingestion/schema_validator.md) |
| [ingestion/metro/affluence.py](ingestion/metro/affluence.py) | [ingestion/metro/affluence.md](ingestion/metro/affluence.md) |
| [ingestion/ecobici/gbfs.py](ingestion/ecobici/gbfs.py) | [ingestion/ecobici/gbfs.md](ingestion/ecobici/gbfs.md) |
| [ingestion/metrobus/gtfs_static.py](ingestion/metrobus/gtfs_static.py) | [ingestion/metrobus/gtfs_static.md](ingestion/metrobus/gtfs_static.md) |
| [ingestion/metrobus/gtfs_rt.py](ingestion/metrobus/gtfs_rt.py) | [ingestion/metrobus/gtfs_rt.md](ingestion/metrobus/gtfs_rt.md) |

## dbt transformation layer

| File | Documentation |
|---|---|
| [dbt_bigquery/dbt_project.yml](dbt_bigquery/dbt_project.yml) | [dbt_bigquery/dbt_project.md](dbt_bigquery/dbt_project.md) |
| [dbt_bigquery/models/staging/sources.yml](dbt_bigquery/models/staging/sources.yml) | [dbt_bigquery/models/staging/sources.md](dbt_bigquery/models/staging/sources.md) |
| [dbt_bigquery/models/staging/stg_metro_affluence.sql](dbt_bigquery/models/staging/stg_metro_affluence.sql) | [dbt_bigquery/models/staging/stg_metro_affluence.md](dbt_bigquery/models/staging/stg_metro_affluence.md) |
| [dbt_bigquery/models/staging/stg_ecobici_station_status.sql](dbt_bigquery/models/staging/stg_ecobici_station_status.sql) | [dbt_bigquery/models/staging/stg_ecobici_station_status.md](dbt_bigquery/models/staging/stg_ecobici_station_status.md) |
| [dbt_bigquery/models/staging/stg_ecobici_station_information.sql](dbt_bigquery/models/staging/stg_ecobici_station_information.sql) | [dbt_bigquery/models/staging/stg_ecobici_station_information.md](dbt_bigquery/models/staging/stg_ecobici_station_information.md) |
| [dbt_bigquery/models/staging/stg_metrobus_stops.sql](dbt_bigquery/models/staging/stg_metrobus_stops.sql) | [dbt_bigquery/models/staging/stg_metrobus_stops.md](dbt_bigquery/models/staging/stg_metrobus_stops.md) |
| [dbt_bigquery/models/staging/stg_metrobus_routes.sql](dbt_bigquery/models/staging/stg_metrobus_routes.sql) | [dbt_bigquery/models/staging/stg_metrobus_routes.md](dbt_bigquery/models/staging/stg_metrobus_routes.md) |
| [dbt_bigquery/models/staging/stg_metrobus_vehicle_positions.sql](dbt_bigquery/models/staging/stg_metrobus_vehicle_positions.sql) | [dbt_bigquery/models/staging/stg_metrobus_vehicle_positions.md](dbt_bigquery/models/staging/stg_metrobus_vehicle_positions.md) |
| [dbt_bigquery/models/marts/mart_metro_affluence_daily.sql](dbt_bigquery/models/marts/mart_metro_affluence_daily.sql) | [dbt_bigquery/models/marts/mart_metro_affluence_daily.md](dbt_bigquery/models/marts/mart_metro_affluence_daily.md) |
| [dbt_bigquery/models/marts/mart_ecobici_availability_2min.sql](dbt_bigquery/models/marts/mart_ecobici_availability_2min.sql) | [dbt_bigquery/models/marts/mart_ecobici_availability_2min.md](dbt_bigquery/models/marts/mart_ecobici_availability_2min.md) |
| [dbt_bigquery/models/marts/mart_metrobus_vehicle_positions_hourly.sql](dbt_bigquery/models/marts/mart_metrobus_vehicle_positions_hourly.sql) | [dbt_bigquery/models/marts/mart_metrobus_vehicle_positions_hourly.md](dbt_bigquery/models/marts/mart_metrobus_vehicle_positions_hourly.md) |

## Infrastructure (Terraform)

| File | Documentation |
|---|---|
| [infra/backend.tf](infra/backend.tf) | [infra/backend.md](infra/backend.md) |
| [infra/providers.tf](infra/providers.tf) | [infra/providers.md](infra/providers.md) |
| [infra/variables.tf](infra/variables.tf) | [infra/variables.md](infra/variables.md) |
| [infra/outputs.tf](infra/outputs.tf) | [infra/outputs.md](infra/outputs.md) |
| [infra/main.tf](infra/main.tf) | [infra/main.md](infra/main.md) |
| [infra/modules/storage/main.tf](infra/modules/storage/main.tf) | [infra/modules/storage/main.md](infra/modules/storage/main.md) |
| [infra/modules/bigquery/main.tf](infra/modules/bigquery/main.tf) | [infra/modules/bigquery/main.md](infra/modules/bigquery/main.md) |
| [infra/modules/iam/main.tf](infra/modules/iam/main.tf) | [infra/modules/iam/main.md](infra/modules/iam/main.md) |
| [infra/modules/cloudrun/main.tf](infra/modules/cloudrun/main.tf) | [infra/modules/cloudrun/main.md](infra/modules/cloudrun/main.md) |
| [infra/modules/scheduler/main.tf](infra/modules/scheduler/main.tf) | [infra/modules/scheduler/main.md](infra/modules/scheduler/main.md) |
| [infra/modules/secrets/main.tf](infra/modules/secrets/main.tf) | [infra/modules/secrets/main.md](infra/modules/secrets/main.md) |
| [infra/modules/dataproc/main.tf](infra/modules/dataproc/main.tf) | [infra/modules/dataproc/main.md](infra/modules/dataproc/main.md) |

## Tests

| File | Documentation |
|---|---|
| [tests/ingestion/test_bq_logger.py](tests/ingestion/test_bq_logger.py) | [tests/ingestion/test_bq_logger.md](tests/ingestion/test_bq_logger.md) |
| [tests/ingestion/test_ckan_client.py](tests/ingestion/test_ckan_client.py) | [tests/ingestion/test_ckan_client.md](tests/ingestion/test_ckan_client.md) |
| [tests/ingestion/test_gbfs_client.py](tests/ingestion/test_gbfs_client.py) | [tests/ingestion/test_gbfs_client.md](tests/ingestion/test_gbfs_client.md) |
| [tests/ingestion/test_gcs_uploader.py](tests/ingestion/test_gcs_uploader.py) | [tests/ingestion/test_gcs_uploader.md](tests/ingestion/test_gcs_uploader.md) |
| [tests/ingestion/test_schema_validator.py](tests/ingestion/test_schema_validator.py) | [tests/ingestion/test_schema_validator.md](tests/ingestion/test_schema_validator.md) |
| [tests/ingestion/ecobici/test_gbfs.py](tests/ingestion/ecobici/test_gbfs.py) | [tests/ingestion/ecobici/test_gbfs.md](tests/ingestion/ecobici/test_gbfs.md) |
| [tests/ingestion/metrobus/test_gtfs_static.py](tests/ingestion/metrobus/test_gtfs_static.py) | [tests/ingestion/metrobus/test_gtfs_static.md](tests/ingestion/metrobus/test_gtfs_static.md) |
| [tests/ingestion/metrobus/test_gtfs_rt.py](tests/ingestion/metrobus/test_gtfs_rt.py) | [tests/ingestion/metrobus/test_gtfs_rt.md](tests/ingestion/metrobus/test_gtfs_rt.md) |
