# BigQuery Query Cost Analysis

## Methodology

Costs estimated via `bq query --dry_run --use_legacy_sql=false`.
Bytes processed converted to USD at **$5/TB** (on-demand pricing, us-central1).
Run each benchmark after the target table is materialised and populated with at
least one full day of data. Paste the actual byte count from the BigQuery job
details panel into the placeholders below.

```bash
# Template — replace <QUERY> with the SQL from each benchmark
bq query \
  --project_id=cdmx-mobility-prod \
  --use_legacy_sql=false \
  --dry_run \
  '<QUERY>'
```

---

## Benchmark 1: fct_ecobici_station_hourly — partition filter benefit

**Hypothesis:** filtering on `service_date` eliminates all but one partition,
dramatically reducing bytes scanned compared to a station-only filter that
forces a full table scan.

```sql
-- A: full scan (no partition filter)
SELECT station_id, AVG(bikes_available_avg)
FROM `cdmx-mobility-prod.marts_cdmx.fct_ecobici_station_hourly`
WHERE station_id = '1'
GROUP BY station_id;
```
Result A: **[N GB]** → **$[X.XX]**

```sql
-- B: partition filter applied
SELECT station_id, AVG(bikes_available_avg)
FROM `cdmx-mobility-prod.marts_cdmx.fct_ecobici_station_hourly`
WHERE service_date = '2026-04-20'
  AND station_id = '1'
GROUP BY station_id;
```
Result B: **[N MB]** → **$[X.XX]**

Saving: **[XX%]**

---

## Benchmark 2: fct_unified_mobility_hourly — cluster benefit on mode

**Hypothesis:** `cluster_by=['mode', 'station_id']` allows BigQuery to skip
blocks for irrelevant modes, reducing bytes for single-mode queries.

```sql
-- A: mode filter without knowing cluster benefit (same partition, all modes)
SELECT mode, COUNT(*) AS event_count
FROM `cdmx-mobility-prod.marts_cdmx.fct_unified_mobility_hourly`
WHERE service_date BETWEEN '2026-04-01' AND '2026-04-30'
  AND mode = 'ecobici'
GROUP BY mode;
```
Result A (clustered): **[N MB]** → **$[X.XX]**

Note: run the same query on an equivalent un-clustered copy of the table to
measure the cluster savings. Use `CREATE TABLE ... CLUSTER BY ()` (no cluster)
as a baseline if needed.

---

## Benchmark 3: fct_metrobus_stop_events — route_id cluster benefit

**Hypothesis:** `cluster_by=['route_id']` prunes blocks for route-level
Tableau queries (a common filter pattern for operations dashboards).

```sql
-- A: route filter on clustered table
SELECT route_id, AVG(headway_minutes) AS avg_headway
FROM `cdmx-mobility-prod.marts_cdmx.fct_metrobus_stop_events`
WHERE service_date BETWEEN '2026-04-01' AND '2026-04-30'
  AND route_id = '1'
GROUP BY route_id;
```
Result A: **[N MB]** → **$[X.XX]**

---

## Benchmark 4: dim_station spatial join — ST_DWITHIN vs ST_DISTANCE

**Hypothesis:** `ST_DWITHIN` short-circuits on the spatial index and is faster
than `ST_DISTANCE(...) < 200` on a CROSS JOIN of the same table.

```sql
-- A: ST_DWITHIN (used in spatial proximity analysis)
SELECT COUNT(*)
FROM `cdmx-mobility-prod.marts_cdmx.dim_station` m
CROSS JOIN `cdmx-mobility-prod.marts_cdmx.dim_station` e
WHERE m.mode = 'metro' AND e.mode = 'ecobici'
  AND ST_DWITHIN(m.geog, e.geog, 200);
```
Result A: **[N MB]** → **$[X.XX]**

```sql
-- B: equivalent ST_DISTANCE < threshold
SELECT COUNT(*)
FROM `cdmx-mobility-prod.marts_cdmx.dim_station` m
CROSS JOIN `cdmx-mobility-prod.marts_cdmx.dim_station` e
WHERE m.mode = 'metro' AND e.mode = 'ecobici'
  AND ST_DISTANCE(m.geog, e.geog) < 200;
```
Result B: **[N MB]** → **$[X.XX]**

Note: `dim_station` is small (~700 rows) so the absolute cost difference will
be negligible — this benchmark is primarily educational. Re-run against
`fct_unified_mobility_hourly` spatial joins if those are added in the future.

---

## Summary Table

| Benchmark | Without optimisation | With optimisation | Saving |
|---|---|---|---|
| 1 — partition filter (ecobici) | [N GB] | [N MB] | [XX%] |
| 2 — cluster filter (mode) | [N MB baseline] | [N MB clustered] | [XX%] |
| 3 — cluster filter (route_id) | [N MB baseline] | [N MB clustered] | [XX%] |
| 4 — ST_DWITHIN vs ST_DISTANCE | [N MB] | [N MB] | [XX%] |

*Fill in after tables are materialised. Actual numbers go in the PR that first*
*runs `dbt build` against production Silver data.*
