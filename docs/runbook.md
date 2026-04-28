# Operations Runbook — cdmx-mobility

This document covers the most common failure modes and their remediation steps.
See [Architecture](../CLAUDE.md) for system context and [cost-estimates.md](cost-estimates.md) for budget notes.

---

## Accessing the Airflow UI

The Airflow webserver runs on the `cdmx-airflow` Compute Engine VM (port 8080).
It is never exposed publicly — access it via an IAP SSH tunnel:

```bash
gcloud compute ssh cdmx-airflow \
  --project=cdmx-mobility-prod \
  --zone=us-central1-a \
  --tunnel-through-iap \
  -- -L 8080:localhost:8080 -N &

# Then open http://localhost:8080   (admin / admin on first boot)
```

To view the webserver without opening a terminal:
```bash
make backfill DATE=2026-04-27   # opens tunnel automatically as a side effect
```

---

## Daily Pipeline Overview

| Time (UTC) | Event |
|---|---|
| ~02:00 | Weather Cloud Scheduler ingest |
| ~04:00 | Metrobús static GTFS Cloud Scheduler job |
| Continuous | EcoBici Cloud Scheduler poll (every 10 min) |
| Continuous | Metrobús email poll (every 5 min) |
| **08:00** | `daily_mobility_pipeline` DAG fires |
| 08:00–08:10 | Stage 1: Cloud Run ingestors triggered |
| 08:10–08:40 | Stage 2: GCS landing sensors |
| 08:40–09:00 | Stage 3: Spark Silver pair 1 (weather + metro) |
| 09:00–09:20 | Stage 3: Spark Silver pair 2 (ecobici + metrobus) |
| 09:20–09:35 | Stage 4: dbt build + test |
| 09:35 | Stage 5: Slack success message |
| **SLA deadline** | **10:00** (2h after schedule) |

---

## Failure Modes

### 1. `wait_metro` sensor times out (CKAN unreachable)

**Symptom:** `wait_for_landing.wait_metro` fails with `AirflowSensorTimeout` after 1 hour.

**Cause:** `datos.cdmx.gob.mx` intermittently blocks GitHub Actions / Cloud Run IPs.
Metro affluence data is a cumulative CSV — missing a single day is acceptable; the
next successful run will cover the gap.

**Diagnosis:**
```sql
-- Check last 5 metro runs in BQ ingestion log
SELECT source, status, error_message, ingested_at
FROM `cdmx-mobility-prod.meta_cdmx.ingestion_log`
WHERE source = 'metro_affluence'
ORDER BY ingested_at DESC
LIMIT 5
```

**Remediation:**
1. In the Airflow UI, click `wait_metro` → **Mark as Skipped**.
2. Downstream tasks will continue without metro data.
3. Once CKAN is reachable, rerun just the metro partition:
   ```bash
   gcloud dataproc workflow-templates instantiate cdmx-spark-metro \
     --region=us-central1 --project=cdmx-mobility-prod \
     --parameters=INPUT_DATE=$(date +%Y-%m-%d)
   ```

---

### 2. Dataproc cluster fails to start (QUOTA_EXCEEDED)

**Symptom:** `spark_silver.spark_ecobici` (or any other Spark task) fails with
`RESOURCE_EXHAUSTED: Quota exceeded for quota metric 'CPUS_ALL_REGIONS'`.

**Cause:** A previous cluster is still terminating, or the quota was temporarily reduced.
The daily pipeline stagger (pair 1 → pair 2) should prevent this, but a stuck cluster
from a previous failed run can occupy the quota.

**Diagnosis:**
```bash
gcloud dataproc clusters list \
  --project=cdmx-mobility-prod \
  --region=us-central1
```

**Remediation:**
```bash
# Delete any stuck cluster
gcloud dataproc clusters delete <cluster-name> \
  --project=cdmx-mobility-prod \
  --region=us-central1 --quiet

# Then in Airflow UI: clear the failed Spark task and re-run.
```

---

### 3. dbt build fails

**Symptom:** `dbt_build` task fails. The task log shows a dbt compilation or runtime error.

**Diagnosis:** SSH into the Airflow VM and run dbt manually against the failing model:
```bash
make airflow-shell
# Inside the container:
cd /opt/dbt_bigquery
dbt build --select <failing_model> --target prod
```
Most failures are either:
- **Missing Silver partition** — the Spark job for that date didn't write data.
  Check BQ ingestion log and re-run the relevant Spark template.
- **BigQuery quota** — check the BigQuery console for RESOURCE_EXHAUSTED errors.
- **Schema drift** — a source column was renamed. Check the dbt compilation error for the column name and update `sources.yml` or the staging model.

**Remediation:** Fix the root cause, then clear and re-run `dbt_build` in the Airflow UI.
If `dbt_test` fails but `dbt_build` succeeded, the data is in Gold — investigate the
test failure in `dbt_bigquery/models/*/schema.yml` before marking it acceptable.

---

### 4. Airflow scheduler stops scheduling tasks

**Symptom:** Tasks stay in `queued` indefinitely. The webserver shows the scheduler
heartbeat as stale (last seen > 5 min ago).

**Diagnosis:**
```bash
make airflow-status     # shows Docker container health
make airflow-logs       # tail scheduler logs
```

**Remediation:**
```bash
make airflow-shell
# or directly:
gcloud compute ssh cdmx-airflow \
  --project=cdmx-mobility-prod \
  --zone=us-central1-a \
  --tunnel-through-iap \
  -- "docker compose -f /opt/cdmx-mobility/orchestration/docker-compose.yml restart airflow-scheduler"
```

If restarting doesn't help, check disk usage (Airflow logs fill fast):
```bash
# Inside the VM:
df -h /opt/airflow/logs
# Logs are shipped to GCS (remote_logging=true); local logs older than 7 days are safe to delete.
find /opt/airflow/logs -mtime +7 -name "*.log" -delete
```

---

### 5. VM reboots (power event / maintenance)

The Airflow Docker Compose services have `restart: unless-stopped`. On a clean boot
they restart automatically. If they don't:

```bash
gcloud compute ssh cdmx-airflow \
  --project=cdmx-mobility-prod \
  --zone=us-central1-a \
  --tunnel-through-iap \
  -- "cd /opt/cdmx-mobility && git pull --ff-only origin main && \
      docker compose -f /opt/cdmx-mobility/orchestration/docker-compose.yml up -d"
```

---

### 6. EcoBici Cloud Run Job failures

**Symptom:** `wait_ecobici` sensor never fires; EcoBici data is missing from GCS.

**Diagnosis:**
```bash
gcloud run jobs executions list \
  --job=ecobici-ingest \
  --project=cdmx-mobility-prod \
  --region=us-central1 \
  --limit=5
```

**Remediation:** Trigger a manual run and inspect logs:
```bash
gcloud run jobs execute ecobici-ingest \
  --project=cdmx-mobility-prod \
  --region=us-central1
```

---

### 7. Weekly quality check reports failures

**Symptom:** `weekly_backfill_check` posts failures to Slack.

**Triage steps:**
1. Note which model failed and which expectation.
2. Query the model directly in BigQuery to inspect the data:
   ```sql
   SELECT * FROM `cdmx-mobility-prod.marts_cdmx.<model>`
   WHERE service_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
   ORDER BY service_date
   ```
3. If data is missing for specific dates, run a targeted backfill:
   ```bash
   make backfill DATE=<missing-date>
   ```
4. If data is present but out of expected range, investigate the upstream source
   (CKAN publish gap, EcoBici API change, etc.) before updating the expectations.

---

## Backfilling Missed Days

### Single day
```bash
make backfill DATE=2026-03-15
```

### Date range
```bash
make backfill-range START=2026-03-01 END=2026-03-31
```

Both commands open an IAP tunnel and trigger the `daily_mobility_pipeline` DAG
for each date. Runs are independent and can execute in parallel
(`max_active_runs=1` prevents the same date from running twice but allows
different dates to queue up). Monitor at http://localhost:8080 after the tunnel opens.

### Manual Spark-only backfill (skip ingest + dbt)
```bash
# Process one date directly via Dataproc (no Airflow needed)
gcloud dataproc workflow-templates instantiate cdmx-spark-metro \
  --region=us-central1 \
  --project=cdmx-mobility-prod \
  --parameters=INPUT_DATE=2026-03-15
```

---

## Cost Controls

| Component | Cost/month |
|---|---|
| Airflow VM (e2-standard-2) | ~$50 |
| Dataproc daily pipeline (4 jobs × $0.19 × 30 days) | ~$23 |
| Dataproc hourly pipeline ($0.19 × 24h × 30 days) | ~$137 |
| Cloud Run ingestors | ~$2 |
| BigQuery + GCS | ~$5 |

**Hourly pipeline cost warning:** Running `hourly_realtime_pipeline` 24h/day adds ~$137/month.
Disable it during off-hours (00:00–07:00 CDMX) once baseline EcoBici metrics are stable:
in the Airflow UI, pause the DAG during those hours or use an Airflow timetable.

The VM can be stopped outside business hours if the daily 08:00 UTC cron is the only
trigger needed:
```bash
gcloud compute instances stop cdmx-airflow \
  --project=cdmx-mobility-prod \
  --zone=us-central1-a
# Start it 30 min before the 08:00 UTC schedule:
gcloud compute instances start cdmx-airflow \
  --project=cdmx-mobility-prod \
  --zone=us-central1-a
```

---

## Secrets Rotation

Airflow secrets (Fernet key, DB password, Slack webhook) are stored in GCP Secret Manager.
To rotate the Slack webhook URL:
```bash
echo -n "https://hooks.slack.com/..." | \
  gcloud secrets versions add airflow-slack-webhook-url \
  --data-file=- \
  --project=cdmx-mobility-prod

# Restart Airflow to pick up the new secret
make airflow-down
make airflow-up
```
