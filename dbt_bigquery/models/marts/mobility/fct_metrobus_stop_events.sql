{{
    config(
        materialized='table',
        partition_by={'field': 'service_date', 'data_type': 'date'},
        cluster_by=['route_id']
    )
}}

with headway as (
    select * from {{ ref('int_metrobus_headway') }}
),

routes_latest as (
    -- deduplicate to most-recent GTFS static ingest per route
    select route_id, route_short_name, route_long_name, route_color
    from {{ ref('stg_metrobus_routes') }}
    qualify row_number() over (partition by route_id order by ingestion_date desc) = 1
),

stops_dim as (
    select station_id as stop_id, station_key, lat, lon, geog, parent_station_id
    from {{ ref('dim_station') }}
    where mode = 'metrobus'
),

dim_dt as (
    select
        date_day,
        day_name,
        is_weekend,
        is_weekday,
        is_public_holiday,
        is_bridge_day,
        is_quincena_payday,
        is_school_vacation,
        holiday_name
    from {{ ref('dim_date') }}
)

select
    {{ dbt_utils.generate_surrogate_key([
        'headway.vehicle_id',
        'headway.stop_id',
        'cast(headway.dwell_start_ts as string)'
    ]) }}                                                           as fct_sk,
    headway.service_date,
    headway.obs_hour,
    headway.route_id,
    r.route_short_name,
    r.route_long_name,
    r.route_color,
    headway.trip_id,
    headway.vehicle_id,
    headway.stop_id,
    headway.stop_name,
    headway.stop_sequence,
    s.station_key,
    s.lat,
    s.lon,
    s.geog,
    s.parent_station_id,
    headway.dwell_start_ts,
    headway.dwell_end_ts,
    headway.dwell_seconds,
    headway.dwell_minutes,
    headway.headway_seconds,
    headway.headway_minutes,
    headway.prev_vehicle_id,
    headway.prev_arrival_ts,
    d.day_name,
    d.is_weekend,
    d.is_weekday,
    d.is_public_holiday,
    d.is_bridge_day,
    d.is_quincena_payday,
    d.is_school_vacation,
    d.holiday_name
from headway
left join routes_latest r using (route_id)
left join stops_dim     s on s.stop_id    = headway.stop_id
left join dim_dt        d on d.date_day   = headway.service_date
