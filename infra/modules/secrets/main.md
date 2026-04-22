# infra/modules/secrets/main.tf

## What it does

Provisions Google Secret Manager secrets used by the pipeline. Creates one `google_secret_manager_secret` resource per secret name using a `for_each` loop. Each secret uses automatic replication (`replication { auto {} }`) so GCP manages the replication policy.

**Note:** This module creates the secret *containers* only — it does not set secret values. Secret values must be added manually after `terraform apply`:

```bash
echo -n "my-secret-value" | gcloud secrets versions add ecobici_api_key --data-file=-
```

## Secrets provisioned

| Secret ID | Purpose |
|---|---|
| `ecobici_api_key` | EcoBici GBFS Bearer token (currently not required — feed is public) |
| `tableau_pat` | Tableau Personal Access Token for publishing workbooks |
| `slack_webhook_url` | Incoming webhook for pipeline alerts |
| `metro_cdmx_rss_url` | RSS feed URL for Metro CDMX announcements |

## How it ties with the rest of the project

- **[infra/modules/iam/main.tf](../iam/main.tf)** — Grants `roles/secretmanager.secretAccessor` to `cdmx-pipeline-sa`, allowing Cloud Run containers to read these secrets at runtime.
- **[infra/modules/cloudrun/main.tf](../cloudrun/main.tf)** — Cloud Run containers can mount secrets as env vars or volumes (not currently configured in Terraform — `CDMX_ECOBICI_API_KEY` is passed as a plain env var for now).
- **[ingestion/config.py](../../../ingestion/config.py)** — `ecobici_api_key` can be injected via `CDMX_ECOBICI_API_KEY` env var; the secret provides the value in Cloud Run.
