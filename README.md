# CDMX Mobility Pipeline
<img width="800" height="436" alt="CDMX-mobility_x2" src="https://github.com/user-attachments/assets/a8969675-1b57-4395-b77a-30bbc81f37a9" />

A data pipeline containing continuously updated mobility data across Mexico City's public transportation network (Metro, Metrobus, Ecobici).

**Link to project:** https://mobility.anuarhage.com

## How It's Made:

**Tech used:** Python, PySpark, dbt (SQL), BigQuery, GCS, Apache Spark, Apache Airflow, FastAPI, Next.js 14, Deck.gl, Recharts, Terraform, Docker, Google Cloud Platform

### The pipeline starts with custom Python ingestors. Each data source has its own ingestor path based on how the data is released:

- Ecobici bike-share system uses a Lyft GBFS API polled every 10 minutes via a Cloud Run Job for up to date information on the bike stations with most use, the stations most often empty or full, and current bike availability.
- Metrobús vehicle positions arrive through an automated email pipeline — a transit data broker sends bus location files every few minutes, which are received by a dedicated endpoint, unpacked, and stored. This powers the stop arrival times, route coverage maps, and headway analysis on the dashboard.
- Metrobús static route data (stops, routes, and schedules) is delivered in the same email and processed once daily to keep the reference information — like which stops belong to which lines — accurate and up to date.
- Metro affluence data is pulled from Mexico City's CKAN open data portal but must run locally since the portal blocks all GCP IP ranges at the TCP level.
- Weather data is fetched daily from Open-Meteo across four zones of the city, capturing hourly temperature, wind, rain, and humidity. This feeds the weather overlays on the dashboard and the analysis of how conditions affect ridership across all three transit modes.

### Bronze to Silver

These transformations run on Dataproc clusters powered by PySpark. The four jobs do the heavy lifting: EcoBici uses a `lag()` window function to deduplicate snapshots and keep only state-change rows (~6–9× compression). Many stations stay the same between each 10 minute polling producing many duplicates, this takes care of that; Metrobús uses H3 spatial indexing at resolution 9 to snap vehicle GPS coordinates to stops and reconstruct dwell sessions; weather pivots Open-Meteo's hourly array format across 4 city zones and derives a Rothfusz heat index and Beaufort wind category. Silver lands as partitioned Parquet in GCS and is exposed to BigQuery via external tables.

### Gold

Gold models are built with dbt. The `fct_ecobici_station_hourly` model is an incremental merge keyed on `(station_id, hour_ts)` with a `QUALIFY ROW_NUMBER()` guard for timezone-boundary edge cases. Metro affluence uses monthly partition granularity instead of daily — the 2010–2026 history would exceed BigQuery's 4,000-partition limit otherwise. The primary source, `fct_unified_mobility_hourly`, joins all three transit modes with weather context into 1.4M rows.

### Orchestration

Orchestration runs on a self-hosted Airflow 2.9.3 on a GCE e2-medium VM, accessed only via IAP tunnel. The four DAGs handle daily ingestion → GCS sensor gates → sequential Spark Silver (sequential because parallel execution hits the project's `IN_USE_ADDRESSES` quota) → Great Expectations validation → dbt build → freshness SLA checks → Slack notification. Monthly Metro and hourly EcoBici pipelines run on separate DAGs.

### Dashboard

The dashboard is Next.js 14 with Recharts for time-series charts and Deck.gl 9 for geospatial maps (stockout choropleth, station picker, corridor map, borough equity layer). It reads from a FastAPI service (`pipeline-api`) with 13 endpoints across routers for pipeline health, ridership pulse, station deep-dives, modal substitution analysis, and accessibility equity scores. All infrastructure is Terraform-managed — Cloud Run, Dataproc workflow templates, BigQuery datasets, IAM, Artifact Registry, and the Airflow VM.

## Optimizations

Metro data is ingested manually once a month meaning I must run the ingestor from a local machine monthly. Originally it was run as a GitHub cron Action as part of the CI. 'datos.cdmx.gob.mx' would block the IP. Tried after as a Cloud Run Job but GCP IP was also blocked. Third option was using The Airflow VM (static IP) but it was also blocked meaning the entire GCP IP range is firewalled. I was left with 2 options either run locally which is a single command once a month or get a Non-GCP VM with a monthly cron, this would add ~4$/month for a single command. The decision was made to run manually/locally to reduce costs.

Metrobus ingestion via email. The metrobus datos requires you to sign up to be able to access their live Metrobus Sinopticoplus data. Sinopticoplus exposes vehicle position data via a request-triggered email containing S3 download links, which the system polls every 5 minutes, receives via SendGrid inbound parse, and downloads automatically. This design adds no extra costs at this scale and it works perfectly.

The dashboard is not designed to be a live view of current positions, it is instead an analytical tool for understanding how Mexico City's transit system performs over time. However Ecobici has near-live snapshots of bike availability directly on the dashboard. While doing this for the other transits would have been much more computationally heavy and expensive, the Ecobici snapshots are self contained and adding near real-time data was straightforward and a welcome bonus. If you wanna explore CDMX transit trends over time while also looking for an available bike in the city you can be confident that bike availability for all stations in the city have daily up to date data..

Massive cloud savings using `cpu_idle = true`. The service receives sinopticoplus GTFS-RT webhooks every 5 minutes during Metrobús operating hours. Each webhook takes ~10 seconds to process. With `cpu_idle = true` (request-based billing), only those ~2,400 active vCPU-seconds per day are billed instead of 86,400. The service still scales to handle incoming webhooks immediately; `cpu_idle` only affects idle billing between requests.

The `metrobus-gtfs-email-ingest` Cloud Run Job was scheduled to run every 5 minutes 24/7 (`*/5 * * * *`), generating 288 invocations/day. Metrobús operates from 04:30 to midnight on regular days and until 01:00 on Fridays and Saturdays. During off-hours (01:00–04:00), sinopticoplus does not transmit GTFS-RT data, so these job runs were wasted. Reduced from 288 to 252 invocations/day (36 fewer per night).

A GCE Instance Schedule Policy (`google_compute_resource_policy` with `instance_schedule_policy`) was attached to the instance to start it and stop it at designated times. This reduces billable compute hours from 720 hours/month to 240 hours/month. (The VM can still be started manually at any time for debugging or backfills)

The Airflow VM was downsized from e2-standard-2 to e2-medium to reduce costs (~60% reduction in costs). e2-small was considered to reduce the costs even more but the RAM would not be sufficient to run at peak task execution comfortably.
