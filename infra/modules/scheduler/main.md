# infra/modules/scheduler/main.tf

## What it does

Provisions two Cloud Scheduler jobs that trigger the Cloud Run batch ingestors on a cron schedule.

## Jobs

### `ecobici-gbfs-poll`

- **Schedule:** `*/2 * * * *` (every 2 minutes)
- **Timezone:** `America/Mexico_City`
- **Target:** HTTP POST to Cloud Run Jobs API → triggers `ecobici-ingest` Job
- **Auth:** OAuth2 token via `cdmx-pipeline-sa` (which has `roles/run.invoker`)
- **Retry:** `retry_count = 0` — if a poll fails, the next 2-minute tick starts fresh.

### `metrobus-gtfs-static-daily`

- **Schedule:** `0 4 * * *` (04:00 AM Mexico City time daily)
- **Timezone:** `America/Mexico_City`
- **Target:** HTTP POST → triggers `metrobus-gtfs-static` Job
- **Auth:** OAuth2 token via `cdmx-pipeline-sa`
- **Retry:** `retry_count = 1` — one retry if the initial trigger fails.

The 04:00 schedule is chosen because SEMOVI typically publishes GTFS updates overnight, so morning runs pick up the latest static feed.

## Trigger mechanism

Cloud Scheduler calls the Cloud Run Jobs API endpoint directly:
```
POST https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job_name}:run
```
No Pub/Sub or intermediary — direct HTTP invocation authenticated by the service account OAuth2 token.

## How it ties with the rest of the project

- **[infra/modules/cloudrun/main.tf](../cloudrun/main.tf)** — Provides `job_name` (`ecobici-ingest`) and `metrobus_static_job_name` (`metrobus-gtfs-static`) used in the scheduler URIs.
- **[infra/modules/iam/main.tf](../iam/main.tf)** — Provides `service_account_email` with `roles/run.invoker` needed to trigger the jobs.
- **[ingestion/ecobici/gbfs.py](../../../ingestion/ecobici/gbfs.py)** — The code executed when `ecobici-ingest` runs.
- **[ingestion/metrobus/gtfs_static.py](../../../ingestion/metrobus/gtfs_static.py)** — The code executed when `metrobus-gtfs-static` runs.
