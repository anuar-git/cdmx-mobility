# infra/outputs.tf

## What it does

Exports key resource identifiers from the root Terraform module. These outputs are printed after every `terraform apply` and can be read programmatically with `terraform output -json`.

## Outputs

| Output | Source | Value |
|---|---|---|
| `bucket_name` | `module.storage` | Name of the GCS raw data bucket (`cdmx-mobility-data`) |
| `bigquery_datasets` | `module.bigquery` | List of BigQuery dataset IDs (`raw_cdmx`, `staging_cdmx`, `marts_cdmx`, `meta_cdmx`) |
| `service_account_email` | `module.iam` | Email of the pipeline service account (`cdmx-pipeline-sa@...`) |
| `wif_provider` | `module.iam` | Full resource name of the Workload Identity Federation provider |

## How it ties with the rest of the project

- **`service_account_email`** — Used when configuring the `GCP_SERVICE_ACCOUNT` GitHub secret for CI Workload Identity Federation.
- **`wif_provider`** — Used as the `WIF_PROVIDER` GitHub secret value for `google-github-actions/auth@v2` in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
- **`bucket_name`** — Confirms the storage bucket name after first apply; matches `CDMX_RAW_BUCKET_NAME` env var used by ingestors.
