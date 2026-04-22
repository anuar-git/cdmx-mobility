# Cost Estimates — cdmx-mobility GCP Platform

All prices are us-central1 on-demand as of April 2026. Actual costs vary with
data volume and run duration. Estimates assume nominal daily runs; the platform
is not yet at steady-state so treat these as upper bounds.

---

## Dataproc ephemeral clusters (Bronze → Silver Spark jobs)

**Cluster spec per job:** 1× n1-standard-4 master + 3× n1-standard-4 workers
= 4 nodes × 4 vCPUs = **16 vCPUs total**.

| Component | Rate | 16 vCPUs / 20 min |
|---|---|---|
| Compute (n1-standard-4) | $0.0475 / vCPU / hr | $0.25 |
| Dataproc premium | $0.010 / vCPU / hr | $0.053 |
| **Total per run** | | **~$0.30** |

Four jobs run daily (EcoBici, Metro, Metrobús, Weather):

| Scenario | Daily cost | Monthly cost |
|---|---|---|
| 4 jobs × 20 min (ephemeral) | **$1.20/day** | **~$36/month** |
| Persistent cluster 24/7 (same spec) | $18.24/day | ~$547/month |
| **Ephemeral saving** | **93%** | **~$511/month** |

Jobs are triggered by Cloud Scheduler at staggered times (02:00, 06:00, 06:30,
07:00 CDMX) so clusters never overlap and the peak concurrent cost is one
cluster at a time.

---

## GCS storage

### Raw Bronze (existing)

| Feed | Approx daily volume | Format |
|---|---|---|
| EcoBici station_status | ~340 K rows × 2 min = ~1 MB/day compressed JSON | NDJSON |
| Metrobús GTFS-RT | ~2,880 snapshots × ~50 KB = ~140 MB/day | NDJSON + .pb |
| Metro affluence | 1 CSV/day, ~2 MB | CSV |
| Weather | 1 JSON/day, <1 MB | JSON |

GCS Standard storage: **$0.020 / GB / month**.
Lifecycle rule moves `metrobus/vehicle_positions_raw/` to NEARLINE after 30 days
($0.010/GB/month) and raw data to COLDLINE after 90 days ($0.004/GB/month).

### Silver Parquet (new)

Parquet with Snappy compression is typically 3–5× smaller than the equivalent
raw JSON/CSV. The EcoBici deduplication step reduces ~340 K rows/day to ~40–80 K
rows/day (~6–9× row reduction), then Parquet compression applies on top.

| Silver table | Estimated daily size | Monthly storage |
|---|---|---|
| ecobici/state_changes | ~5 MB/day | ~$0.003/month |
| metro/affluence | ~0.1 MB/day | <$0.001/month |
| metrobus/stop_events | ~10 MB/day | ~$0.006/month |
| weather/hourly_fact | ~0.5 MB/day | <$0.001/month |
| **Total Silver** | **~16 MB/day** | **~$0.01/month** |

Silver storage cost is negligible — the benefit is query performance (external
Parquet tables in BigQuery scan far less data than raw JSON) and the Spark
deduplication already paid for itself by reducing downstream BQ slot consumption.

---

## BigQuery

External tables over GCS are queried on-demand. The Silver Parquet tables are
the primary query target for dbt marts and Tableau.

| Usage | Rate | Estimate |
|---|---|---|
| dbt build (all marts, daily) | $5 / TB scanned | ~$0.005/day (small Silver volume) |
| Tableau dashboard refreshes | $5 / TB scanned | ~$0.01/day (cached after first load) |
| **Monthly BQ total** | | **<$1/month** |

BQ costs will grow proportionally with Silver data accumulation. At 1 year of
EcoBici data (~1.7 GB Silver) a full mart rebuild scans <2 GB → <$0.01 per run.

---

## Cloud Run (ingestors)

| Service | Invocations | Cost |
|---|---|---|
| EcoBici GBFS (every 10 min) | ~4,320/month | ~$0.02/month |
| Metrobús GTFS-RT daemon (always-on, 1 vCPU) | 720 hr/month | ~$15/month |
| Metrobús GTFS static (daily) | ~30/month | <$0.01/month |
| Metro affluence (daily via CI) | ~30/month | CI runner cost |

The GTFS-RT daemon dominates Cloud Run cost. It runs at minimum instance count
= 1 to avoid cold-start gaps in the vehicle position time-series.

---

## Cloud Scheduler

$0.10 / job / month after the free tier of 3 jobs. This project has 7 scheduler
jobs → **$0.40/month**.

---

## Monthly total (steady state)

| Component | Est. monthly cost |
|---|---|
| Dataproc (4 jobs × 30 days) | ~$36 |
| Cloud Run GTFS-RT daemon | ~$15 |
| GCS storage (Bronze + Silver) | ~$5 |
| BigQuery queries | <$1 |
| Cloud Run (batch jobs) | ~$1 |
| Cloud Scheduler | ~$0.40 |
| **Total** | **~$58/month** |

The dominant cost is Dataproc. If Silver jobs are only needed weekly (e.g.
Metro affluence is released monthly), changing the scheduler from daily to
weekly reduces Dataproc to ~$8/month and total to ~$30/month.
