# infra/modules/cloudrun/main.tf

## What it does

Provisions the container registry and all Cloud Run compute resources for the ingestion platform: two Cloud Run **Jobs** (batch ingestors) and one Cloud Run **Service** (always-on daemon). Also creates a Cloud Monitoring alert policy for daemon health.

## Resources

### `google_artifact_registry_repository.ingestor`

Docker registry `ingestor` in `us-central1`. CI pushes the ingestor image here; Cloud Run pulls from it.

Registry URI: `us-central1-docker.pkg.dev/cdmx-mobility-prod/ingestor/ingestor`

### `google_cloud_run_v2_job.ecobici_ingest`

**Job name:** `ecobici-ingest`

Runs `uv run python main.py ingest-ecobici-gbfs` inside the ingestor container.

| Setting | Value |
|---|---|
| Resources | 1 CPU, 512 Mi |
| Max retries | 0 (Cloud Scheduler handles retry) |
| Service account | `cdmx-pipeline-sa` |

Env vars set: `CDMX_GCP_PROJECT_ID`, `CDMX_RAW_BUCKET_NAME`, `CDMX_ECOBICI_GBFS_BASE_URL`, `CDMX_ECOBICI_API_KEY` (empty — public feed).

### `google_cloud_run_v2_job.metrobus_gtfs_static`

**Job name:** `metrobus-gtfs-static`

Runs `uv run python main.py ingest-metrobus-gtfs-static`.

| Setting | Value |
|---|---|
| Resources | 1 CPU, 512 Mi |
| Max retries | 1 |
| Service account | `cdmx-pipeline-sa` |

Env vars set: `CDMX_GCP_PROJECT_ID`, `CDMX_RAW_BUCKET_NAME`, `CDMX_METROBUS_GTFS_STATIC_DATASET_ID`.

### `google_cloud_run_v2_service.metrobus_gtfs_rt_daemon`

**Service name:** `metrobus-gtfs-rt-daemon`

Always-on daemon running `uv run python main.py run-metrobus-gtfs-rt-daemon`.

| Setting | Value |
|---|---|
| Min instances | 1 (never scale to zero) |
| Max instances | 1 (single daemon) |
| Resources | 0.5 CPU, 256 Mi |
| Ingress | `INGRESS_TRAFFIC_INTERNAL_ONLY` |
| Concurrency | 1 request at a time |
| Startup probe | GET `/healthz:8080`, 5s delay, 3 failures |
| Liveness probe | GET `/healthz:8080`, 30s period, 3 failures |

The `/healthz` endpoint is served by `_HealthHandler` in [`ingestion/metrobus/gtfs_rt.py`](../../../ingestion/metrobus/gtfs_rt.py).

### `google_monitoring_alert_policy.gtfs_rt_daemon_down`

Fires if the GTFS-RT service has zero healthy instances for 5 minutes (`duration = "300s"`). Auto-closes after 7 days. Notification channels are not wired here — add Slack/PagerDuty channels after first apply.

## Outputs

| Output | Value |
|---|---|
| `job_name` | `ecobici-ingest` |
| `metrobus_static_job_name` | `metrobus-gtfs-static` |
| `image_registry` | Artifact Registry base URI |

## How it ties with the rest of the project

- **[infra/modules/scheduler/main.tf](../scheduler/main.tf)** — Uses `job_name` and `metrobus_static_job_name` outputs to construct Cloud Scheduler HTTP targets.
- **[Dockerfile](../../../Dockerfile)** — The image built here provides the container for all three resources.
- **[.github/workflows/ci.yml](../../../.github/workflows/ci.yml)** — `build-and-push` job pushes to the Artifact Registry repo created here.
- **[ingestion/metrobus/gtfs_rt.py](../../../ingestion/metrobus/gtfs_rt.py)** — Implements the health server on `:8080` required by the liveness/startup probes.

> **Note:** `metrobus_gtfs_rt_vehicle_positions_url` defaults to `""`. The service is deployed but the daemon will fail on every poll until the URL is set in `terraform.tvars` and `terraform apply` is re-run.
