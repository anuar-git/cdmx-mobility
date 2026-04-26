{{
    config(
        materialized='table',
        partition_by={'field': 'service_date', 'data_type': 'date'},
        cluster_by=['mode', 'station_id']
    )
}}

-- One row per (mode, station_id, route_id, hour_ts).
-- EcoBici: already at hourly grain from fct_ecobici_station_hourly.
-- Metrobús: aggregated from stop-event grain to hourly per stop per route.
-- Metro: daily grain only — join to dim_date via service_date in downstream queries.
-- Weather joined by hour; condition label joined via comfort_score BETWEEN range.
-- Surrogate key includes mode to prevent namespace collisions between EcoBici GBFS
-- station IDs and Metrobús GTFS stop IDs.

with ecobici as (
    select
        service_date,
        hour_ts,
        'ecobici'                                                   as mode,
        station_id,
        station_key,
        cast(null as string)                                        as route_id,
        -- ecobici availability metrics
        bikes_available_avg,
        bikes_available_min,
        docks_available_avg,
        stockout_minutes,
        full_minutes,
        state_changes_count,
        observed_minutes,
        availability_ratio,
        fill_ratio,
        -- metrobus metrics (null for ecobici)
        cast(null as integer)                                       as vehicle_count,
        cast(null as float64)                                       as avg_dwell_minutes,
        cast(null as float64)                                       as avg_headway_minutes,
        cast(null as integer)                                       as stop_event_count
    from {{ ref('fct_ecobici_station_hourly') }}
),

metrobus_hourly as (
    select
        service_date,
        obs_hour                                                    as hour_ts,
        stop_id                                                     as station_id,
        station_key,
        route_id,
        count(*)                                                    as stop_event_count,
        count(distinct vehicle_id)                                  as vehicle_count,
        avg(dwell_minutes)                                          as avg_dwell_minutes,
        avg(headway_minutes)                                        as avg_headway_minutes
    from {{ ref('fct_metrobus_stop_events') }}
    group by service_date, obs_hour, stop_id, station_key, route_id
),

metrobus as (
    select
        service_date,
        hour_ts,
        'metrobus'                                                  as mode,
        station_id,
        station_key,
        route_id,
        -- ecobici metrics (null for metrobus)
        cast(null as float64)                                       as bikes_available_avg,
        cast(null as float64)                                       as bikes_available_min,
        cast(null as float64)                                       as docks_available_avg,
        cast(null as float64)                                       as stockout_minutes,
        cast(null as float64)                                       as full_minutes,
        cast(null as integer)                                       as state_changes_count,
        cast(null as float64)                                       as observed_minutes,
        cast(null as float64)                                       as availability_ratio,
        cast(null as float64)                                       as fill_ratio,
        -- metrobus availability metrics
        vehicle_count,
        avg_dwell_minutes,
        avg_headway_minutes,
        stop_event_count
    from metrobus_hourly
),

combined as (
    select * from ecobici
    union all
    select * from metrobus
),

weather as (
    select * from {{ ref('int_weather_city_hourly') }}
),

dim_dt as (
    select
        date_day,
        day_name,
        iso_week,
        is_weekend,
        is_weekday,
        is_public_holiday,
        is_bridge_day,
        is_quincena_payday,
        is_school_vacation,
        holiday_name
    from {{ ref('dim_date') }}
),

condition_dim as (
    select condition_label, comfort_score_min, comfort_score_max
    from {{ ref('dim_weather_condition') }}
)

select
    {{ dbt_utils.generate_surrogate_key([
        'c.mode',
        'c.station_id',
        'coalesce(c.route_id, \'\')',
        'cast(c.hour_ts as string)'
    ]) }}                                                           as fct_sk,
    c.service_date,
    c.hour_ts,
    c.mode,
    c.station_id,
    c.station_key,
    c.route_id,
    -- ecobici metrics
    c.bikes_available_avg,
    c.bikes_available_min,
    c.docks_available_avg,
    c.stockout_minutes,
    c.full_minutes,
    c.state_changes_count,
    c.observed_minutes,
    c.availability_ratio,
    c.fill_ratio,
    -- metrobus metrics
    c.vehicle_count,
    c.avg_dwell_minutes,
    c.avg_headway_minutes,
    c.stop_event_count,
    -- weather
    w.temperature_c,
    w.humidity_pct,
    w.precipitation_mm,
    w.windspeed_ms,
    w.heat_index,
    w.comfort_score,
    w.wind_category,
    w.is_rainy,
    w.is_adverse_weather,
    wc.condition_label                                              as weather_condition,
    -- date attributes
    d.day_name,
    d.iso_week,
    d.is_weekend,
    d.is_weekday,
    d.is_public_holiday,
    d.is_bridge_day,
    d.is_quincena_payday,
    d.is_school_vacation,
    d.holiday_name
from combined c
left join weather          w  on  w.obs_hour          = c.hour_ts
left join condition_dim    wc on  w.comfort_score      between wc.comfort_score_min
                                                           and wc.comfort_score_max
left join dim_dt           d  on  d.date_day           = c.service_date
