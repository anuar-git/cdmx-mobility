{{ config(materialized='ephemeral') }}

-- Headway = time between consecutive vehicle arrivals at the same stop on the
-- same route. Partitioned by (stop_id, route_id, service_date) so the first
-- vehicle of the day gets a NULL headway rather than an inflated cross-day gap.
-- Values > 2 hours are nullified: they indicate either the first vehicle of the
-- day, a data gap from a missed poll cycle, or a route suspension.

with stop_events as (
    select *
    from {{ ref('stg_silver_metrobus_stop_events') }}
),

with_lag as (
    select
        vehicle_id,
        stop_id,
        stop_name,
        route_id,
        trip_id,
        stop_sequence,
        dwell_start_ts,
        dwell_end_ts,
        dwell_seconds,
        dwell_minutes,
        service_date,
        timestamp_trunc(dwell_start_ts, hour)                          as obs_hour,
        lag(dwell_start_ts) over (
            partition by stop_id, route_id, service_date
            order by dwell_start_ts
        )                                                               as prev_arrival_ts,
        lag(vehicle_id) over (
            partition by stop_id, route_id, service_date
            order by dwell_start_ts
        )                                                               as prev_vehicle_id
    from stop_events
),

with_headway as (
    select
        *,
        timestamp_diff(dwell_start_ts, prev_arrival_ts, second)        as headway_seconds_raw
    from with_lag
)

select
    vehicle_id,
    stop_id,
    stop_name,
    route_id,
    trip_id,
    stop_sequence,
    dwell_start_ts,
    dwell_end_ts,
    dwell_seconds,
    dwell_minutes,
    service_date,
    obs_hour,
    prev_vehicle_id,
    prev_arrival_ts,
    -- NULL for first vehicle of day or gaps > 2 h
    case
        when headway_seconds_raw between 0 and 7200 then headway_seconds_raw
    end                                                                 as headway_seconds,
    case
        when headway_seconds_raw between 0 and 7200
            then headway_seconds_raw / 60.0
    end                                                                 as headway_minutes
from with_headway
