# ADR-002: Apache Spark on Dataproc for Bronze → Silver Transformations

**Status:** Accepted
**Date:** 2026-04-19
**Author:** anuar-git

---

## Context

The Bronze layer (raw GCS) contains data in four formats: CSV (Metro affluence, Metrobús
GTFS static), NDJSON (Metrobús GTFS-RT vehicle positions, EcoBici GBFS snapshots), and raw
protobuf (Metrobús GTFS-RT archival). The Silver layer must clean, conform, and partition
this data into columnar Parquet so that downstream dbt Gold models run fast and cheap.

Three tools could do this work: BigQuery SQL (via scheduled queries or dbt), Dataflow
(managed Beam), or Spark on Dataproc. This ADR records which was chosen and why.

---

## Decisions

### 1. Spark over BigQuery SQL for Bronze → Silver

**Decision:** Spark on Dataproc handles all Bronze → Silver transforms.
**Counter-position:** BigQuery SQL could handle some of these as scheduled queries or
dbt models reading from BQ external tables.

Three transforms are not viable in pure BigQuery SQL:

**a) GTFS-RT protobuf parsing**
Raw protobuf (`.pb` files under `metrobus/vehicle_positions_raw/`) is not a format
BigQuery can ingest natively. The NDJSON companion files are ingestible, but they are
pre-parsed by the daemon — the `.pb` archive is the source of truth for reprocessing and
backfills. Parsing `gtfs_realtime_pb2.FeedMessage` requires `gtfs-realtime-bindings` and
Python; Spark with a Python UDF is the natural host.

**b) EcoBici windowed deduplication**
EcoBici produces ~720 snapshots/day × ~470 stations = ~338,400 rows/day. Over a week that
is 2.4M rows. The deduplication logic is:

```
lag(num_bikes_available) OVER (PARTITION BY station_id ORDER BY snapshot_ts)
```

A BigQuery scheduled query could run this. The problem is cost and design philosophy:
running a `LAG()` window over 2.4M rows in BigQuery invokes a distributed query billed at
$5/TB. Over a month of backfill (10M+ rows) that becomes non-trivial. More importantly,
the result is a structural Silver dataset — it should be produced by a replayable batch
job, not a scheduled SQL query that accumulates state over a live table. Spark processes
the raw snapshots once, writes Parquet once, and the output is immutable and reprocessable.

**c) Trajectory reconstruction for Metrobús vehicles**
Stop snapping (projecting a GPS position to the nearest stop along the vehicle's assigned
route) and dwell detection (identifying when a vehicle is stationary near a stop for >30s)
are iterative operations: for each position, look up the H3 neighbors, join to the stops
table, compute time deltas within each vehicle's session. This involves a spatial join
(H3 index lookup) followed by a session-window aggregation — two operations that require
careful partition management. Spark's in-memory shuffle and explicit `.repartition()` /
`.cache()` control make the data layout predictable. BigQuery would require nested CTEs
and implicit full-table scans on every run.

**Where to draw the line:** Silver → Gold stays in dbt/BigQuery SQL. Once data is clean
Parquet partitioned by date, aggregations like `mart_metro_affluence_daily` and
`mart_metrobus_vehicle_positions_hourly` are simple GROUP BYs that BQ handles cheaply and
fast. SQL is the right tool there. Spark is justified only for the three cases above.

---

### 2. Ephemeral Dataproc clusters, not a persistent cluster

**Decision:** Each Spark job runs on a freshly provisioned, dedicated Dataproc cluster
that is torn down after the job completes (workflow template with `managed_cluster`).

**Cost comparison (us-central1, 2026 pricing):**

| Configuration | Hourly rate | Daily cost |
|---|---|---|
| 1 master + 3 workers, `n1-standard-4` | ~$0.92/hr | — |
| Persistent cluster (24/7) | $0.92/hr | **~$22/day** |
| Ephemeral cluster (4 jobs × 20 min/day) | 4 × ($0.92 × 0.33 hr) | **~$1.24/day** |

Ephemeral saves ~94% (~$620/month). The marginal cost per job run is ~$0.31, less than a
coffee. This is the number to quote when asked about cost awareness.

Breakdown per node: `n1-standard-4` VM = $0.190/hr + Dataproc premium ($0.010/vCPU × 4
vCPUs) = $0.040/hr → $0.230/hr per node. Four nodes = $0.920/hr. Dataproc bills per-second
with a 1-minute minimum, so a 20-minute run is billed as exactly 20 minutes.

Additional benefits of ephemeral:
- No cluster state to manage; each run starts from a clean image.
- Cluster version upgrades happen at job submit time by changing `image_version` in
  Terraform — no rolling restart.
- Autoscaling policy not needed; cluster size is fixed per job type and right-sized.

---

### 3. Plain Parquet for Silver, not Delta Lake

**Decision:** Silver output files are plain Parquet, partitioned by `service_date` (and
`route_id` for Metrobús vehicle events). Delta Lake is not used for the Silver layer.

`delta-spark` is already declared as a project dependency (`pyproject.toml`) and was
evaluated. It was not chosen for Silver for three reasons:

**a) BigQuery external table compatibility**
BigQuery can read plain Parquet partitioned in Hive-style directory layout
(`service_date=YYYY-MM-DD/part-*.parquet`) via `HIVE_PARTITIONING_MODE = "AUTO"` with no
connector required. Delta Lake tables include a `_delta_log/` transaction log that BigQuery
cannot interpret — the external table would read all Parquet files including compaction
artifacts and produce duplicates unless carefully filtered.

**b) Read path complexity**
Delta requires Spark (or the Delta Standalone reader) to read correctly. Plain Parquet can
be read by BigQuery, Spark, pandas, DuckDB, and the `gcloud` `bq` CLI — no lock-in to a
single reader.

**c) No ACID upserts needed at Silver**
Delta's primary value is ACID upserts and time-travel. Silver is an append/overwrite layer:
each daily job overwrites `service_date=YYYY-MM-DD` partitions with the latest reprocessed
output. `spark.write.partitionBy("service_date").mode("overwrite")` is idempotent and
sufficient. There is nothing to upsert.

**When to revisit:** If a future phase requires merging late-arriving GTFS-RT records into
an existing Silver partition (e.g., a vehicle position that crosses midnight), Delta's
`MERGE INTO` would be the correct tool. At that point, convert the affected Silver table
to Delta and update the downstream BigQuery source to use the
`google-cloud-bigquery-storage` connector with Delta support.

---

## Pre-condition Status (as of 2026-04-19)

| Source | Bronze flowing | Notes |
|---|---|---|
| Metro affluence | ✅ | CI job on every push to `main`; first run 2026-04-18 |
| EcoBici GBFS | ✅ | Cloud Run Job every 2 min via Cloud Scheduler; live since 2026-04-17 |
| Metrobús GTFS static | ✅ | CI job + Cloud Run Job daily 04:00 |
| Metrobús GTFS-RT | ⚠️ | Data arrives via SendGrid Inbound Parse webhook (`inbound_webhook.py`) from sinopticoplus — no polling URL required. `metrobus-gtfs-inbound` Cloud Run Service is defined in Terraform but not yet deployed; blocked on `metrobus_inbound_webhook_secret` being set in `terraform.tvars`. Once applied, Bronze NDJSON accumulates at the same GCS paths as the daemon. |

The webhook deployment gap does not block the other three Silver jobs. The Metrobús Silver
job will be smoke-tested against static GTFS stop data first; NDJSON validation follows
once the `metrobus-gtfs-inbound` service is live.

---

## Consequences

- Four Spark jobs will be maintained in `spark_jobs/`. Any change to the Bronze schema
  (e.g., CKAN adds a column to the Metro affluence CSV) requires updating the corresponding
  Silver job and its test fixture.
- Dataproc `image_version = "2.2-debian12"` pins the Spark version to 3.5.x. Upgrading
  requires testing the jobs against the new image locally before changing Terraform.
- Silver Parquet partitions are overwritten on each run. Downstream BigQuery external tables
  must use `HIVE_PARTITIONING_MODE = "AUTO"` to pick up new partitions without a table
  schema refresh.
