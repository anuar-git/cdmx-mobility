# infra/variables.tf

## What it does

Declares all input variables for the root Terraform module. Values are supplied via [`terraform.tvars`](terraform.tvars) (gitignored for secrets) or overridden on the CLI with `-var`. A `terraform.tvars.example` is committed as a template.

## Variables

| Variable | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `project_id` | string | — | **yes** | GCP project ID (e.g. `cdmx-mobility-prod`) |
| `region` | string | `us-central1` | no | GCP region for Cloud Run, Dataproc, Scheduler |
| `bq_location` | string | `US` | no | Multi-region location for BigQuery datasets |
| `data_bucket_name` | string | `cdmx-mobility-raw` | no | Name of the GCS raw data bucket |
| `ingestor_image` | string | `""` | no | Container image URI for Cloud Run Jobs/Service |
| `ecobici_gbfs_base_url` | string | `""` | no | EcoBici GBFS feed root URL |
| `metrobus_gtfs_static_dataset_id` | string | `gtfs` | no | CKAN dataset slug for SEMOVI unified CDMX GTFS |
| `metrobus_gtfs_rt_vehicle_positions_url` | string | `""` | no | GTFS-RT protobuf endpoint URL (obtain from SEMOVI) |

## How it ties with the rest of the project

- **[infra/main.tf](main.tf)** — Passes these variables into each module (e.g., `var.data_bucket_name` → `module.storage`, `var.ingestor_image` → `module.cloudrun`).
- **[infra/terraform.tvars](terraform.tvars)** — Sets the actual values; not committed (see `.gitignore`).
- **[infra/terraform.tvars.example](terraform.tvars.example)** — Committed template showing expected keys without secret values.
- **`metrobus_gtfs_rt_vehicle_positions_url`** — Currently empty in `terraform.tvars`. Must be set before applying `module.cloudrun` to deploy the GTFS-RT daemon service.
