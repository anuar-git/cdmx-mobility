# infra/main.tf

## What it does

The root Terraform orchestration file. It instantiates all seven infrastructure modules in dependency order, wiring outputs from one module as inputs to the next. No resources are defined directly here — all resource definitions live in the modules.

## Module instantiation order

```
storage → bigquery → iam → dataproc → secrets → cloudrun → scheduler
```

| Module | Source | Key inputs | Key outputs |
|---|---|---|---|
| `storage` | `./modules/storage` | `bucket_name`, `location` | `bucket_name` |
| `bigquery` | `./modules/bigquery` | `project_id`, `location`, `raw_bucket_name` (← storage) | `dataset_ids` |
| `iam` | `./modules/iam` | `project_id`, `bucket_name` (← storage) | `service_account_email`, `wif_provider` |
| `dataproc` | `./modules/dataproc` | `project_id`, `region`, `service_account_email` (← iam) | — |
| `secrets` | `./modules/secrets` | *(no inputs — creates secrets unconditionally)* | — |
| `cloudrun` | `./modules/cloudrun` | `project_id`, `region`, `service_account_email` (← iam), `image`, `raw_bucket_name` (← storage), GTFS-RT/GBFS URLs | `job_name`, `metrobus_static_job_name` |
| `scheduler` | `./modules/scheduler` | `project_id`, `region`, `job_name` (← cloudrun), `metrobus_static_job_name` (← cloudrun), `service_account_email` (← iam) | — |

## How to apply

```bash
cd infra/
terraform init
terraform plan -var-file="terraform.tvars"
terraform apply -var-file="terraform.tvars"
```

## How it ties with the rest of the project

- **[infra/variables.tf](variables.tf)** — All `var.*` references in this file are declared there.
- **[infra/outputs.tf](outputs.tf)** — Surfaces module outputs to the operator after apply.
- **[infra/backend.tf](backend.tf)** — Remote state configuration; must be initialized before applying.
- **[infra/terraform.tvars](terraform.tvars)** — Actual values for `project_id`, `ingestor_image`, URLs, etc.
