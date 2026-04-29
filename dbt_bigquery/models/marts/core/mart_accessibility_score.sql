{{
    config(
        materialized='table'
    )
}}

-- Transit accessibility score per station: how many distinct modes exist within 500 m?
-- Weights reflect service capacity: Metro = 3, Metrobús = 2, EcoBici = 1.
-- Score is normalized 0–100 across all stations.
--
-- Borough assignment is intentionally omitted here — the frontend groups stations
-- into alcaldías using Turf.js booleanPointInPolygon against alcaldias.geojson.
-- This keeps the spatial join logic out of BigQuery and avoids a polygon seed.
--
-- Performance note: the self-join on ST_DISTANCE is O(n²) over 8 K stations.
-- The bounding-box pre-filter reduces ST_DISTANCE calls by ~99 % before the
-- exact distance check; BigQuery handles the remainder in a single scan pass.

with all_stations as (
    select
        station_key,
        station_id,
        station_name,
        mode,
        lat,
        lon,
        geog
    from {{ ref('dim_station') }}
    where geog is not null
),

-- At 19 °N: 0.005 ° ≈ 556 m (lat) and 524 m (lon) — generous 500 m pre-filter.
nearby_modes as (
    select
        s1.station_key,
        s1.station_id,
        s1.station_name,
        s1.mode,
        s1.lat,
        s1.lon,
        count(distinct s2.mode)                                                     as nearby_mode_count,
        sum(
            case s2.mode
                when 'metro'    then 3
                when 'metrobus' then 2
                else 1
            end
        )                                                                           as accessibility_score_raw,
        countif(s2.mode = 'metro')                                                  as nearby_metro_count,
        countif(s2.mode = 'metrobus')                                               as nearby_metrobus_count,
        countif(s2.mode = 'ecobici')                                                as nearby_ecobici_count
    from all_stations s1
    left join all_stations s2
        on  s1.station_key != s2.station_key
        and abs(s1.lat - s2.lat) < 0.005
        and abs(s1.lon - s2.lon) < 0.005
        and st_distance(s1.geog, s2.geog) <= 500
    group by 1, 2, 3, 4, 5, 6
),

score_bounds as (
    select
        max(accessibility_score_raw) as max_score,
        min(accessibility_score_raw) as min_score
    from nearby_modes
)

select
    n.station_key,
    n.station_id,
    n.station_name,
    n.mode,
    n.lat,
    n.lon,
    n.nearby_mode_count,
    n.accessibility_score_raw,
    round(
        safe_divide(
            n.accessibility_score_raw - b.min_score,
            b.max_score - b.min_score
        ) * 100,
        1
    )                                                                               as accessibility_score,
    n.nearby_metro_count,
    n.nearby_metrobus_count,
    n.nearby_ecobici_count

from nearby_modes n
cross join score_bounds b
