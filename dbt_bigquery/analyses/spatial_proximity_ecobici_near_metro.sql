-- Spatial proximity analysis: EcoBici stations near Metro stations.
--
-- Two queries:
--   Query 1 — EcoBici within 200 m of a Metro station (multimodal interchange map).
--   Query 2 — Median walk distance to nearest EcoBici per Metro line (analytical).
--
-- Both use ST_DWITHIN for the filter (faster than ST_DISTANCE < threshold because
-- BigQuery can short-circuit the spatial index scan). ST_DISTANCE is then called
-- only on the surviving pairs to get the exact metre value.
--
-- dim_station is small (~200 Metro + ~450 EcoBici rows after live data populates),
-- so a CROSS JOIN is acceptable. If the table grows significantly, replace with
-- a geohash-bucketed semi-join.
--
-- To compile: cd dbt_bigquery && uv run dbt compile --select spatial_proximity_ecobici_near_metro
-- Compiled SQL will be at: target/compiled/.../spatial_proximity_ecobici_near_metro.sql
--
-- To materialise Query 1 as a persistent table for a Tableau interchange map layer:
--   Option A (recommended): promote to a dbt model in marts/core/geo_ecobici_near_metro.sql
--   Option B: BigQuery scheduled query — prepend:
--     CREATE OR REPLACE TABLE `{{ target.project }}.marts_cdmx.geo_ecobici_near_metro` AS

-- ─────────────────────────────────────────────────────────────────────────────
-- Query 1: EcoBici stations within 200 m of a Metro station
-- Enables a Tableau "multimodal interchange" map layer — stations where a rider
-- can bike to Metro within a ~2-minute walk.
-- ─────────────────────────────────────────────────────────────────────────────
select
    m.station_id                                        as metro_station_id,
    m.station_name                                      as metro_station_name,
    m.linea,
    m.borough,
    e.station_id                                        as ecobici_station_id,
    e.station_name                                      as ecobici_station_name,
    e.capacity                                          as ecobici_capacity,
    round(st_distance(m.geog, e.geog))                  as distance_meters
from {{ ref('dim_station') }} m
cross join {{ ref('dim_station') }} e
where m.mode = 'metro'
  and e.mode = 'ecobici'
  and m.geog is not null
  and e.geog is not null
  and st_dwithin(m.geog, e.geog, 200)
order by distance_meters;

-- ─────────────────────────────────────────────────────────────────────────────
-- Query 2: Median walk distance to nearest EcoBici per Metro line (within 500 m)
-- Surfaces which Metro lines are best served by EcoBici in proximity terms.
-- Pairs beyond 500 m are excluded — beyond that walking is the dominant mode
-- rather than cycling.
-- ─────────────────────────────────────────────────────────────────────────────
with pairs_500m as (
    select
        m.station_id                                    as metro_station_id,
        m.linea,
        e.station_id                                    as ecobici_station_id,
        round(st_distance(m.geog, e.geog))              as distance_meters
    from {{ ref('dim_station') }} m
    cross join {{ ref('dim_station') }} e
    where m.mode = 'metro'
      and e.mode = 'ecobici'
      and m.geog is not null
      and e.geog is not null
      and st_dwithin(m.geog, e.geog, 500)
),

nearest_per_metro_station as (
    -- one row per Metro station: distance to its closest EcoBici station
    select
        metro_station_id,
        linea,
        min(distance_meters)                            as nearest_ecobici_m
    from pairs_500m
    group by metro_station_id, linea
)

select
    linea,
    count(*)                                            as metro_stations_with_ecobici_500m,
    round(approx_quantiles(nearest_ecobici_m, 100)[offset(50)])
                                                        as median_nearest_ecobici_m,
    round(min(nearest_ecobici_m))                       as min_nearest_ecobici_m,
    round(max(nearest_ecobici_m))                       as max_nearest_ecobici_m
from nearest_per_metro_station
group by linea
order by median_nearest_ecobici_m;
