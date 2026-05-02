# Key Decisions

A running record of architectural and product decisions made during development,
including context and trade-offs discussed at the time.

---

## Real-time dashboard data — EcoBici vs. Metrobús

**Date:** 2026-04-30
**Status:** Decision made — no real-time Metrobús; EcoBici real-time under consideration

### Background

The dashboards query `marts_cdmx` BigQuery tables. These tables are only updated once
per day when the Airflow `daily_mobility_pipeline` DAG runs at 08:00 UTC. Despite the
high-frequency ingestion schedulers (EcoBici every 10 min, Metrobús every 5 min), the
dashboard shows data that is 1–2 days old because it never queries Bronze or Silver
directly.

### Pipeline layers and their cadences

The pipeline has three distinct layers operating at very different frequencies:

| Layer | What it is | Cadence |
|---|---|---|
| **Bronze** (GCS) | Raw ingestion — NDJSON/CSV snapshots landing in GCS | EcoBici every 10 min, Metrobús every 5 min, Weather daily, Metro daily |
| **Silver** (Spark/Parquet) | Cleaned, conformed Parquet on GCS; read via BigQuery external tables | Once daily — Airflow triggers Dataproc at 08:00 UTC |
| **Gold** (dbt/BigQuery) | Aggregated mart tables in `marts_cdmx`; what the dashboard queries | Once daily — dbt runs after Silver in the same Airflow DAG |

The high-frequency collection cadence exists for **data completeness** (not missing any
snapshot), not for real-time dashboard availability. All dashboard endpoints query Gold.

### Why 1–2 days of lag

When the Airflow DAG runs on April 30 at 08:00 UTC:
- Spark processes Bronze data accumulated through April 29
- dbt rebuilds Gold tables from the updated Silver

April 30 data is still accumulating in Bronze and will not appear in the dashboard until
May 1's pipeline run. This is by design — daily ridership aggregates are only meaningful
once a day is complete.

### EcoBici vs. Metrobús real-time feasibility

Both modes ingest raw data at high frequency, but the computation required to produce
a meaningful metric differs significantly:

**EcoBici — straightforward**
Each Bronze snapshot is self-contained: `bikes_available = 5` means 5 bikes are
available right now. A live availability metric requires only a simple aggregation over
the Silver external table. No reprocessing needed.

**Metrobús — computationally heavier**
A raw position record `(vehicle_id, lat, lon, timestamp)` is not ridership. Computing
stop events requires:
1. Spatially snapping each position to the nearest stop (H3 resolution 9, ~174 m hexagons)
2. Detecting dwell *sessions* — contiguous observations at the same stop, gap ≤ 60 s,
   duration ≥ 30 s — across a sequence of positions
3. Computing headways from session boundaries

This session detection logic runs across a time window, not a single snapshot. It is
currently implemented in the Spark job (`bronze_to_silver_metrobus_vehicles.py`).
Re-implementing it incrementally in BigQuery SQL or running Spark more frequently
(e.g. hourly) is feasible but not a small change.

### Decision

- **Metrobús real-time:** Not pursued. The session detection complexity and the batch
  nature of the stop-events metric make it a poor fit for incremental real-time queries.
  The once-daily Airflow pipeline is sufficient.

- **EcoBici real-time:** Under consideration. A new API endpoint querying the Silver
  external table (`silver_cdmx.ecobici_state_changes`) directly could surface live
  station availability without waiting for the daily dbt run. No decision taken yet.

- **Metro:** Inherently historical. The source is a CKAN batch dump covering the full
  historical record. Real-time is not applicable.

---

## Airflow SA Cloud Run permissions — invoker + viewer over developer

**Date:** 2026-05-01
**Status:** Decision made

### Background

The `daily_mobility_pipeline` DAG uses `CloudRunJobOperator` to trigger Cloud Run jobs
(EcoBici ingest, Metrobús static, Metrobús email, weather ingest). The operator triggers
the job and then polls the resulting long-running operation via `run.operations.get` to
wait for completion.

The Airflow SA (`cdmx-airflow-sa`) was initially granted `roles/run.invoker`, which only
covers triggering. When Airflow tried to poll operation status it received:

```
403 Permission 'run.operations.get' denied
```

### Options considered

| Option | Permissions granted | Risk |
|---|---|---|
| `roles/run.developer` | Trigger + poll + **create/update/delete** Cloud Run resources | Excessive — SA could modify or delete production jobs |
| `roles/run.invoker` + `roles/run.viewer` | Trigger + read-only (get executions, poll operations) | Least privilege — no write access beyond triggering |
| Custom role with `run.operations.get` only | Minimal | More Terraform maintenance overhead |

### Decision

Use `roles/run.invoker` + `roles/run.viewer`. The viewer role includes `run.operations.get`
and other read-only permissions (list executions, get job state) without granting any
ability to create, update, or delete Cloud Run resources. This satisfies least-privilege
while keeping the Terraform simple.

---

## Metro affluence ingestion — manual local run (Option C)

**Date:** 2026-05-02
**Status:** Decision made — manual local ingestion; automated options ruled out

### Background

The metro affluence dataset (`datos.cdmx.gob.mx`) releases a new cumulative historical
CSV roughly once a month. Three automation paths were evaluated:

| Option | Approach | Outcome |
|---|---|---|
| GitHub Actions cron | Already in CI | Blocked — datos.cdmx.gob.mx firewalls GitHub Actions IP ranges |
| GCE Airflow VM (static IP) | BashOperator in monthly DAG | Blocked — TCP connection times out; entire GCP IP range is firewalled at TCP level |
| Cloud Run Job | Same image as other ingestors | Blocked — same GCP IP range |
| Non-GCP VM (Hetzner/DO) | ~$4/month VM, monthly cron | Works, not pursued — disproportionate infrastructure for one monthly HTTP call |
| Local machine | `uv run python main.py ingest-metro-affluence` | Works instantly — local ISP IP is not blocked |

Testing confirmed: `curl` from the Airflow VM to `189.240.234.183:443` times out with
no TCP connection established. The same request from a local machine returns 200 in
under a second.

### Decision

Run the metro ingestor manually from a local machine once per month after CKAN releases
new data (typically mid-month for the prior month). The `monthly_metro_pipeline` DAG
sensor (`GCSObjectsWithPrefixExistenceSensor`, up to 25-day timeout) fires automatically
once the Bronze partition lands in GCS — no further manual steps required after upload.
