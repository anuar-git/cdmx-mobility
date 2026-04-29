{{
    config(
        materialized='table',
        partition_by={
            'field': 'service_date',
            'data_type': 'date',
            'granularity': 'month'
        },
        cluster_by=['metro_line']
    )
}}

-- Modal substitution analysis: for each Metro line and service date, how does
-- nearby Metrobús and EcoBici activity track with Metro ridership?
--
-- "Low-service days" are days where metro_daily_entries < 85 % of the 7-day
-- rolling average for that line — used as a proxy for service disruptions since
-- we have no incident data.
--
-- Used by Dashboard 3 (Modal Substitution Explorer) to surface the substitution
-- signal: when Metro dips, do nearby alternative-mode metrics rise?

with metro_stops as (
    select
        station_key,
        station_id                      as station_canonical,
        station_name,
        linea                           as metro_line,
        lat,
        lon,
        geog
    from {{ ref('dim_station') }}
    where mode = 'metro'
      and geog is not null
),

metro_ridership as (
    select
        service_date,
        linea                           as metro_line,
        sum(daily_entries)              as metro_daily_entries
    from {{ ref('fct_metro_affluence_daily') }}
    group by 1, 2
),

-- Metrobús stops within 300 m of any stop on each Metro line.
-- Distinct so a Metrobús stop near multiple Metro stops is counted once per line.
metrobus_near_metro as (
    select distinct
        m.metro_line,
        b.station_key                   as metrobus_station_key
    from metro_stops m
    inner join {{ ref('dim_station') }} b
        on  b.mode = 'metrobus'
        and b.geog is not null
        and abs(m.lat - b.lat) < 0.003
        and abs(m.lon - b.lon) < 0.003
        and st_distance(m.geog, b.geog) <= 300
),

ecobici_near_metro as (
    select distinct
        m.metro_line,
        e.station_key                   as ecobici_station_key
    from metro_stops m
    inner join {{ ref('dim_station') }} e
        on  e.mode = 'ecobici'
        and e.geog is not null
        and abs(m.lat - e.lat) < 0.003
        and abs(m.lon - e.lon) < 0.003
        and st_distance(m.geog, e.geog) <= 300
),

metrobus_daily as (
    select
        mnm.metro_line,
        f.service_date,
        count(*)                        as nearby_metrobus_events,
        count(distinct f.vehicle_id)    as nearby_metrobus_vehicles
    from metrobus_near_metro mnm
    inner join {{ ref('fct_metrobus_stop_events') }} f
        on mnm.metrobus_station_key = f.station_key
    group by 1, 2
),

ecobici_daily as (
    select
        enm.metro_line,
        f.service_date,
        sum(f.state_changes_count)      as nearby_ecobici_trips,
        avg(f.availability_ratio)       as nearby_ecobici_availability
    from ecobici_near_metro enm
    inner join {{ ref('fct_ecobici_station_hourly') }} f
        on enm.ecobici_station_key = f.station_key
    group by 1, 2
),

metro_rolling as (
    select
        service_date,
        metro_line,
        metro_daily_entries,
        avg(metro_daily_entries) over (
            partition by metro_line
            order by service_date
            rows between 6 preceding and current row
        )                               as metro_7d_avg
    from metro_ridership
)

select
    mr.service_date,
    mr.metro_line,
    mr.metro_daily_entries,
    round(mr.metro_7d_avg, 0)                                       as metro_7d_avg,
    round(safe_divide(mr.metro_daily_entries, mr.metro_7d_avg), 4)  as metro_vs_avg_ratio,
    mr.metro_daily_entries < mr.metro_7d_avg * 0.85                 as is_low_service_day,
    coalesce(bd.nearby_metrobus_events, 0)                          as nearby_metrobus_events,
    coalesce(bd.nearby_metrobus_vehicles, 0)                        as nearby_metrobus_vehicles,
    coalesce(ed.nearby_ecobici_trips, 0)                            as nearby_ecobici_trips,
    ed.nearby_ecobici_availability                                  as nearby_ecobici_availability

from metro_rolling mr
left join metrobus_daily bd
    on  mr.metro_line = bd.metro_line
    and mr.service_date = bd.service_date
left join ecobici_daily ed
    on  mr.metro_line = ed.metro_line
    and mr.service_date = ed.service_date
