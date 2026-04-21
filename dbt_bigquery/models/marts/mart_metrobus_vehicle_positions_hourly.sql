{{
    config(
        materialized="table",
        partition_by={"field": "hour", "data_type": "timestamp", "granularity": "hour"},
        cluster_by=["route_id"],
    )
}}

with base as (
    select * from {{ ref('stg_metrobus_vehicle_positions') }}
),

hourly as (
    select
        timestamp_trunc(snapshot_at, hour) as hour,
        route_id,
        vehicle_id,
        avg(latitude)                      as avg_latitude,
        avg(longitude)                     as avg_longitude,
        avg(speed_ms)                      as avg_speed_ms,
        count(*)                           as snapshot_count
    from base
    where route_id is not null
        and vehicle_id is not null
    group by 1, 2, 3
)

select * from hourly
