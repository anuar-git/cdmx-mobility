# CDMX Mobility Platform

A data engineering and analytics platform for Mexico City's public transit network. It ingests real-time and historical data from three mobility modes — Metro, Metrobús, and EcoBici — combines them with weather observations, and surfaces the results through an interactive analytical dashboard.

---

## What It Does

The platform answers operational and planning questions about Mexico City mobility:

- How does Metro ridership vary by line, station, and day across 16 years of historical data?
- Which EcoBici stations run out of bikes most often, and for how long?
- When a Metro station is underserved, are there nearby Metrobús stops or EcoBici docks that absorb the demand?
- Which neighborhoods have the weakest multi-modal transit access?
- How does weather — rain, heat, humidity — affect EcoBici trip volume at each station?

---

## Data Sources

| Source | Mode | Cadence | Coverage |
|---|---|---|---|
| CKAN / datos.cdmx.gob.mx | Metro affluence | Monthly batch dump | 2010 – present |
| sinopticoplus (email → SendGrid) | Metrobús GTFS-RT + static | Every 5 min / daily | 2026-04-19 – present |
| Lyft GBFS | EcoBici station status | Every 10 min | 2026-04-17 – present |
| Open-Meteo | Weather (5 city zones) | Hourly | 2026-04-21 – present |

Metro data is a cumulative historical dump refreshed monthly. Metrobús and EcoBici data accumulate continuously. Weather is fetched daily for the preceding 24 hours.

**Ingestion tooling:** Python + `httpx` (HTTP client) + `tenacity` (retry logic), packaged as Cloud Run Jobs and Services triggered by Cloud Scheduler. Metro uses a `CKANClient`; EcoBici uses a `GBFSClient`; Metrobús RT arrives via a SendGrid inbound-parse webhook decoded with `gtfs-realtime-bindings` + `protobuf`. All ingestors write raw files to GCS and log run metadata (row counts, byte counts, status) to BigQuery via `google-cloud-bigquery`.

---

## Architecture

The pipeline follows a three-layer medallion architecture on GCP:

```
Bronze  ──  Raw files land in GCS as they arrive
            (NDJSON, CSV, Protobuf snapshots)
            Tools: Cloud Run Jobs/Services · Cloud Scheduler · GCS · SendGrid webhook
              │
              ▼
Silver  ──  PySpark jobs on ephemeral Dataproc clusters clean,
            conform, and deduplicate each source into Parquet.
            Runs once daily at 08:00 UTC via Airflow.
            Tools: PySpark · Dataproc (n1-standard-2 × 4 nodes) · H3 (spatial indexing)
                   Airflow 2.9.3 · Great Expectations (data quality validation)
              │
              ▼
Gold    ──  dbt models in BigQuery aggregate Silver into
            dimension tables, fact tables, and analytical marts.
            Runs daily after Silver completes.
            Tools: dbt 1.9 · BigQuery · dbt_utils · dbt_date · dbt_expectations
              │
              ▼
API     ──  FastAPI service (Cloud Run) exposes 18 read-only
            endpoints querying the Gold tables.
            Tools: FastAPI · google-cloud-bigquery · Cloud Run (IAM-authenticated)
              │
              ▼
Dashboard── Next.js SPA queries the API and renders
            interactive charts and Deck.gl maps.
            Tools: Next.js 14 · Recharts · Deck.gl 9 · react-map-gl 7 · Mapbox GL
```

Data freshness in the dashboard is inherently one day behind: daily aggregates are only meaningful once a full calendar day is complete, so the pipeline processes yesterday's data each morning.

---

## Dashboard Pages

### City Pulse (`/pulse`)
Operational snapshot updated each morning.
- Weather banner: temperature, humidity, precipitation, comfort score, adverse-weather flag
- Daily ridership trend lines for Metro (last month), Metrobús, and EcoBici (last 8 days)
- Deck.gl map of the 20 most bike-starved EcoBici stations, sized by stockout minutes and colored by availability ratio
- Sortable detail table of stockout stations

**Tools:** Recharts `LineChart` (per-mode ridership trends) · Deck.gl `ScatterplotLayer` (stockout map, radius = √stockout\_minutes, color = availability ratio)

---

### Station Explorer (`/station`)
Deep dive into any EcoBici station.
- City-wide clickable station map (677 stations) — click to select, or use the dropdown
- Hourly availability area chart for any date range
- Temperature vs trips scatter plot (weather sensitivity)
- 7-day demand forecast with average ± standard deviation bands by hour
- Nearby multi-mode stations map (500 m radius) with hover tooltips showing live bike counts

**Tools:** Deck.gl `ScatterplotLayer` (city-wide station picker + neighbors map) · Recharts `AreaChart` (hourly availability) · Recharts `ScatterChart` (weather sensitivity) · Recharts `BarChart` (forecast bands) · react-map-gl + Mapbox dark-v11

---

### Modal Substitution (`/modal`)
Explores whether riders shift between modes.
- Metro line picker with 30-day average ridership
- Dual-axis chart: Metro daily ridership vs nearby Metrobús activity and EcoBici trips
- Reference line marking low-service days
- 300 m corridor map showing all Metro + alternative stops along the line

**Tools:** Recharts `ComposedChart` with dual Y-axes and `ReferenceLine` · Deck.gl `ScatterplotLayer` (corridor map, color-coded by mode)

---

### Equity (`/equity`)
Accessibility analysis by borough.
- Multi-mode proximity score (0–100) per station derived from walking distance to alternatives
- GeoJSON choropleth of CDMX boroughs colored by average accessibility score
- Per-borough bar charts: average score and stockout exposure

**Tools:** Turf.js (spatial aggregation of station scores into borough polygons) · Deck.gl `GeoJsonLayer` (choropleth) · Recharts `BarChart` (horizontal, two charts side by side)

---

### Pipeline Health (`/pipeline`)
Observability for the data pipeline itself.
- Freshness SLA cards per data source (EcoBici ≤ 10 min, Metrobús ≤ 60 min, Metro ≤ 24 h, weather ≤ 2 h)
- 30-day ingestion volume (rows + bytes) stacked area chart
- dbt test pass rate trend line
- dbt model runtime bar chart

**Tools:** Recharts `AreaChart` (ingestion volume) · Recharts `LineChart` (test pass rate) · Recharts `BarChart` (runtimes) · BigQuery `meta_cdmx` observability tables (ingestion\_log, dbt\_run\_results, dbt\_test\_results, freshness\_sla\_log)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Ingestion | Python + httpx + tenacity, containerized on Cloud Run |
| Orchestration | Airflow 2.9.3 (self-hosted on GCE e2-medium, Docker Compose) |
| Batch transforms | PySpark on ephemeral Dataproc (n1-standard-2 × 4 nodes) |
| Spatial indexing | H3 resolution 9 (~174 m hexagons) for Metrobús stop snapping |
| Data warehouse | BigQuery (external Parquet tables for Silver, native tables for Gold) |
| SQL transforms | dbt 1.9 + dbt_utils, dbt_date, dbt_expectations |
| Data quality | Great Expectations 1.3.10 (ephemeral + pandas, runs in Airflow) |
| API | FastAPI + google-cloud-bigquery, deployed on Cloud Run |
| Dashboard | Next.js 14 + Recharts + Deck.gl 9 + react-map-gl 7 |
| Maps | Mapbox GL (dark-v11 basemap) + Turf.js (spatial aggregation) |
| Infrastructure | Terraform 1.9.5 on GCP (GCS, BigQuery, Cloud Run, Dataproc, Secret Manager) |
| CI/CD | GitHub Actions — lint, test, Docker build/push, dbt docs to GitHub Pages |

---

## Monthly Operations

Most of the pipeline runs fully automatically. One manual step is required each month:

### Metro affluence ingestion

`datos.cdmx.gob.mx` (the CKAN source) blocks all GCP IP ranges at the TCP level, so
the ingestor cannot run from Cloud Run or the Airflow VM. Run it locally after CKAN
releases the new monthly dump (typically mid-month for the prior month):

```bash
cd /path/to/cdmx-mobility
CDMX_GCP_PROJECT_ID=cdmx-mobility-prod uv run python main.py ingest-metro-affluence
```

Once the CSV lands in GCS, the `monthly_metro_pipeline` Airflow DAG detects it
automatically (sensor polls hourly, waits up to 25 days) and triggers the Spark
Bronze→Silver job — no further action needed.

To check whether CKAN has released new data before running:

```bash
curl -s 'https://datos.cdmx.gob.mx/api/3/action/package_show?id=afluencia-diaria-del-metro-cdmx' \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['result']; print(r['metadata_modified'], r['resources'][0]['name'])"
```

---

## Key Design Decisions

**Why Spark for Bronze→Silver?** The session detection logic for Metrobús (spatially snapping vehicle positions to stops, then finding dwell sessions across a time window) requires stateful processing over ordered sequences of records. BigQuery SQL alone handles this poorly at the raw position granularity. See `docs/adr/002-spark-for-bronze-to-silver.md`.

**Why no real-time Metrobús?** Each raw Metrobús record is a GPS coordinate, not a ridership count. Converting it to a meaningful metric requires spatial snapping (H3 resolution 9) and dwell-session detection across a rolling time window — a batch operation, not a single-snapshot aggregation. EcoBici availability is self-contained per snapshot and feasible for near-real-time. See `docs/key-decisions.md`.

**Why monthly partitions on Metro fact tables?** The historical Metro dataset covers 2010–2026 (~5,800 days × ~195 stations = 1.16M rows). Daily partitioning would exceed BigQuery's 4,000-partition limit. Monthly granularity gives ~195 partitions while the underlying data remains daily.

---

## Repository Layout

```
ingestion/        HTTP ingestors for all four data sources
spark_jobs/       PySpark Bronze→Silver transform jobs
dbt_bigquery/     dbt project — staging, intermediate, marts, seeds, snapshots
api/              FastAPI service (18 endpoints across 5 routers)
dashboard/        Next.js 14 dashboard (5 pages)
orchestration/    Airflow DAGs, Docker Compose stack, helper scripts
infra/            Terraform modules for all GCP resources
docs/             Architecture decisions and cost estimates
tests/            pytest suite for ingestion and Spark jobs
```
