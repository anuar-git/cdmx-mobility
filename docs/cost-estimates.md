# Cost Estimates — cdmx-mobility GCP Platform

All prices are us-central1 on-demand as of April 2026. Estimates are based on
actual April 28 2026 SKU-level billing data and adjusted for normal Airflow-triggered
pipeline runs. The original estimate was missing the Airflow VM entirely; this
document reflects the corrected picture.

---

## Airflow VM (Compute Engine)

The VM runs Docker Compose with postgres, airflow-scheduler, and airflow-webserver.
Downgraded from e2-standard-2 to e2-medium in April 2026 and placed on an
automatic start/stop schedule (see Key Decisions).

| Component | Rate | Monthly |
|---|---|---|
| Compute (e2-medium, 8 hr/day via instance schedule) | $0.027/hr × 8 × 30 | $6.48 |
| Boot disk (50 GB pd-balanced) | $0.10/GB/mo | $5.00 |
| **Total** | | **~$11.50/month** |

Schedule: starts **07:30 UTC** (01:30 CDMX), stops **15:30 UTC** (09:30 CDMX).
Continuous ingestors (EcoBici, Metrobús email) run as Cloud Run Jobs triggered
by Cloud Scheduler and are unaffected by the VM being stopped.

---

## Dataproc ephemeral clusters (Bronze → Silver Spark jobs)

**Cluster spec per job:** 1× n1-standard-2 master + 3× n1-standard-2 workers
= 4 nodes × 2 vCPUs = **8 vCPUs total**.

| Component | Rate | 8 vCPUs / ~18 min |
|---|---|---|
| Compute (n1-standard-2) | $0.0475/vCPU/hr | $0.11 |
| Dataproc premium | $0.010/vCPU/hr | $0.024 |
| **Total per run** | | **~$0.14** |

Four jobs run daily (EcoBici, Metro, Metrobús, Weather), always triggered by
Airflow with `INPUT_DATE={{ ds }}` to scope each run to a single Bronze partition:

| Scenario | Daily cost | Monthly cost |
|---|---|---|
| 4 jobs × ~18 min (ephemeral, scoped) | **$0.56/day** | **~$17/month** |

Jobs are triggered in two parallel pairs (weather + metro, then ecobici + metrobus)
to respect the 10-vCPU `CPUS_ALL_REGIONS` quota — clusters never overlap.

---

## GCS Storage and Operations

The largest GCS cost is **Class A operations** (writes + lists), not storage bytes.
Spark jobs generate hundreds of list calls per run when scanning Silver partition
directories; BigQuery also lists Silver partitions for every dbt build.

| SKU | Source | Monthly est. |
|---|---|---|
| Multi-Region Class A ops (~70K/day) | Spark Silver writes + dbt partition discovery | ~$12/month |
| Multi-Region Class B ops (~55K/day) | Spark Bronze reads | ~$3/month |
| Network transfer (GCS Multi-Region → us-central1) | Dataproc reading Bronze data | ~$3/month |
| Standard storage (Bronze + Silver, ~10 GB/month growth) | All feeds | ~$2/month |
| **Total GCS** | | **~$20/month** |

Note: the GCS bucket (`cdmx-mobility-data`) is Multi-Region (US), which doubles
the Class A/B operation rates vs a Regional (us-central1) bucket ($0.10 vs $0.05
per 10K Class A ops). Migrating to a regional bucket would save ~$9/month but
requires a full data migration — bucket location is immutable after creation.

---

## Cloud Run

### `metrobus-gtfs-inbound` service

This service receives sinopticoplus GTFS-RT webhooks. Originally billed at the
instance-based rate (CPU always allocated), meaning 86,400 vCPU-seconds/day
regardless of actual traffic. Fixed in April 2026 by adding `cpu_idle = true`
(see Key Decisions).

| Billing mode | Daily vCPU-seconds billed | Monthly cost |
|---|---|---|
| Instance-based (original) | 86,400 (24 hr continuous) | ~$46/month |
| **Request-based (current)** | **~2,400 (~240 webhooks × 10 sec)** | **~$1.4/month** |

### Ingestor jobs

| Job | Schedule | Monthly invocations | Monthly cost |
|---|---|---|---|
| `ecobici-ingest` | `*/10 * * * *` | ~4,320 | ~$8/month |
| `metrobus-gtfs-email-ingest` | `*/5 0,4-23 * * *` | ~7,560 | ~$5/month |
| `metrobus-gtfs-static` | `0 4 * * *` | ~30 | <$0.10/month |
| `weather-ingest` | `0 2 * * *` | ~30 | <$0.10/month |
| **Total jobs** | | | **~$13/month** |

---

## BigQuery

External tables over Silver GCS Parquet are the primary query target.

| Usage | Rate | Monthly |
|---|---|---|
| dbt build (daily, small Silver volume) | $5/TB scanned | ~$1/month |
| Streaming inserts (ingestion_log) | $0.01/200MB | <$0.01/month |
| **Total BQ** | | **<$1/month** |

---

## Cloud Scheduler

8 scheduler jobs → 5 billed at $0.10/job/month after the 3-job free tier:
**~$0.50/month**.

---

## Monthly total (current)

| Component | Est. monthly cost |
|---|---|
| Airflow VM (e2-medium, 8 hr/day scheduled) | ~$11.50 |
| GCS operations + storage + transfer | ~$20 |
| Cloud Run jobs (ecobici + metrobus, scoped hours) | ~$13 |
| Dataproc (4 jobs × 30 days, scoped) | ~$17 |
| Cloud Run service (`metrobus-gtfs-inbound`) | ~$1.4 |
| BigQuery | <$1 |
| Cloud Scheduler | ~$0.50 |
| **Total** | **~$64/month** |

---

## Cost history

| Period | Monthly projection | Notes |
|---|---|---|
| Original estimate (pre-launch) | ~$58/month | Airflow VM missing from estimate entirely |
| April 2026 actual (first 10 days) | ~$102/month | VM running 24/7, Cloud Run instance-based billing, manual Spark runs inflating GCS ops |
| After April 2026 optimizations (round 1) | ~$77/month | cpu_idle fix, metrobus scheduler, VM downgrade to e2-medium |
| **After April 2026 optimizations (round 2)** | **~$64/month** | VM start/stop schedule added (8 hr/day) |

---

## Key Decisions

### 1. `cpu_idle = true` on `metrobus-gtfs-inbound` Cloud Run service

**Saving: ~$45/month**

The `metrobus-gtfs-inbound` Cloud Run service was billing at the **instance-based**
rate — CPU allocated continuously 24/7 (86,400 vCPU-seconds/day) regardless of
actual traffic. This was caused by the `cpu_idle` flag not being set in the
Terraform resource, which defaults to always-on CPU allocation.

The service receives sinopticoplus GTFS-RT webhooks every 5 minutes during
Metrobús operating hours. Each webhook takes ~10 seconds to process. With
`cpu_idle = true` (request-based billing), only those ~2,400 active vCPU-seconds
per day are billed instead of 86,400. The service still scales to handle incoming
webhooks immediately; `cpu_idle` only affects idle billing between requests.

File changed: `infra/modules/cloudrun/main.tf` — added `cpu_idle = true` to the
`metrobus-gtfs-inbound` container resources block.

---

### 2. Metrobús email scheduler restricted to operating hours

**Saving: ~$1.3/month**

The `metrobus-gtfs-email-ingest` Cloud Run Job was scheduled to run every 5
minutes 24/7 (`*/5 * * * *`), generating 288 invocations/day. Metrobús operates
from 04:30 to midnight on regular days and until 01:00 on Fridays and Saturdays.
During off-hours (01:00–04:00), sinopticoplus does not transmit GTFS-RT data, so
these job runs were wasted.

The schedule was changed to `*/5 0,4-23 * * *`, which skips hours 01:00–03:59
(the guaranteed dead zone across all days). This covers:
- Regular days (Mon–Thu, Sun): 04:00–00:55 ✓ (service runs 04:30–midnight)
- Fri/Sat extended service: 04:00–00:55 ✓ (service runs 04:30–01:00; last poll at 00:55 captures finishing rides)

Reduced from 288 to 252 invocations/day (36 fewer per night).

File changed: `infra/modules/scheduler/main.tf` — updated `schedule` on
`google_cloud_scheduler_job.metrobus_gtfs_email`.

---

### 4. Airflow VM scheduled start/stop (8 hours/day)

**Saving: ~$13/month**

The Airflow VM was running 24/7 despite only being needed for the daily pipeline
window. The daily pipeline fires at 08:00 UTC and consistently completes by
~14:00 UTC (observed from `meta_cdmx.ingestion_log`). Continuous ingestors
(EcoBici every 10 min, Metrobús email every 5 min) run as Cloud Run Jobs
triggered by Cloud Scheduler and have no dependency on the VM.

A GCE **Instance Schedule Policy** (`google_compute_resource_policy` with
`instance_schedule_policy`) was attached to the instance to start it at
**07:30 UTC** (30-minute buffer before the DAG fires, to allow Docker containers
to come up) and stop it at **15:30 UTC** (90-minute buffer after typical pipeline
completion). This reduces billable compute hours from 720/month to 240/month.

The Compute Engine service agent (`service-PROJECT@compute-system.iam.gserviceaccount.com`)
requires `roles/compute.instanceAdmin.v1` to execute the scheduled start/stop
actions — added as a project IAM binding in the same module.

The VM can still be started manually at any time for debugging or backfills:
```bash
gcloud compute instances start cdmx-airflow --zone=us-central1-a --project=cdmx-mobility-prod
```
The schedule resumes automatically at the next scheduled time.

Files changed: `infra/modules/airflow_vm/main.tf` — added
`google_compute_resource_policy.airflow_schedule`, `data.google_project.project`,
`google_project_iam_member.compute_system_instance_admin`, and
`resource_policies` on the compute instance.

---

### 3. Airflow VM downgraded from e2-standard-2 to e2-medium

**Saving: ~$29/month**

The Airflow VM was provisioned as `e2-standard-2` (2 dedicated vCPUs, 8 GB RAM,
$0.067/hr) but the actual workload does not require 8 GB. The stack runs three
Docker containers (postgres:15-alpine, airflow-scheduler, airflow-webserver) using
LocalExecutor. Idle memory footprint is ~1,200 MB across all three containers plus
the OS. Peak usage during task execution (dbt build, GX validation) adds ~500 MB
for Python subprocesses spawned by LocalExecutor.

`e2-medium` (2 shared vCPUs, 4 GB RAM, $0.027/hr) provides ~2,800 MB of headroom
above the idle baseline — sufficient for peak task execution without risk of
OOM kills. Terraform applies this change in-place (stop → resize → restart) with
no data loss, enabled by `allow_stopping_for_update = true`.

**e2-small was considered and rejected.** e2-small (2 shared vCPUs, 2 GB RAM,
$0.013/hr) would save an additional ~$10/month over e2-medium but leaves only
~800 MB free after idle containers. LocalExecutor spawns task subprocesses inside
the scheduler process; dbt build alone consumes 300–500 MB and GX validation
(pandas + BigQuery client) similarly. Either task running alongside normal
scheduler + webserver + postgres activity would risk exhausting available RAM,
causing the OS to swap or OOM-kill the scheduler — resulting in missed daily
pipeline runs. The $10/month saving does not justify that operational risk.

File changed: `infra/modules/airflow_vm/main.tf` — updated `machine_type` from
`"e2-standard-2"` to `"e2-medium"`.
