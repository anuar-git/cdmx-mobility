# infra/modules/iam/main.tf

## What it does

Provisions the service account and identity configuration that the pipeline uses to authenticate with GCP — both at runtime (Cloud Run, Dataproc) and in CI/CD (GitHub Actions via Workload Identity Federation).

## Resources

### `google_service_account.pipeline` — `cdmx-pipeline-sa`

The single service account used by all runtime components. IAM roles granted:

| Role | Scope | Purpose |
|---|---|---|
| `roles/storage.objectAdmin` | Bucket-scoped | Read/write GCS objects in the data bucket |
| `roles/bigquery.dataEditor` | Project-scoped | Create/update BigQuery tables (dbt writes, ingestion log) |
| `roles/bigquery.jobUser` | Project-scoped | Execute BigQuery queries |
| `roles/dataproc.worker` | Project-scoped | Dataproc cluster worker permissions |
| `roles/secretmanager.secretAccessor` | Project-scoped | Read secrets from Secret Manager |
| `roles/run.invoker` | Project-scoped | Allows Cloud Scheduler to trigger Cloud Run Jobs |

### Workload Identity Federation (WIF)

Enables GitHub Actions to authenticate as `cdmx-pipeline-sa` using short-lived OIDC tokens — **no service account JSON keys required**.

- **Pool:** `github-pool` — OIDC pool for GitHub Actions.
- **Provider:** `github-provider` — Maps `assertion.sub` → `google.subject`, restricts to repository `anuarhage/cdmx-mobility` via `attribute_condition`.
- **Impersonation binding:** Grants the `anuarhage/cdmx-mobility` principal set `roles/iam.workloadIdentityUser` on `cdmx-pipeline-sa`.

## Outputs

| Output | Value |
|---|---|
| `service_account_email` | `cdmx-pipeline-sa@{project}.iam.gserviceaccount.com` |
| `wif_provider` | Full WIF provider resource name (used as `WIF_PROVIDER` GitHub secret) |

## How it ties with the rest of the project

- **[infra/main.tf](../../main.tf)** — Passes `service_account_email` to `module.dataproc`, `module.cloudrun`, and `module.scheduler`.
- **[infra/outputs.tf](../../outputs.tf)** — Surfaces `service_account_email` and `wif_provider` for GitHub secret configuration.
- **[.github/workflows/ci.yml](../../../.github/workflows/ci.yml)** — `google-github-actions/auth@v2` uses `WIF_PROVIDER` and `GCP_SERVICE_ACCOUNT` secrets (the values produced here) for keyless authentication.
- **[infra/modules/cloudrun/main.tf](../cloudrun/main.tf)** — All Cloud Run resources run as this service account.
