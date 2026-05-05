{{ config(materialized='ephemeral') }}

with state_changes as (
    select *
    from {{ ref('stg_silver_ecobici_state_changes') }}
),

with_next as (
    select
        station_id,
        service_date,
        snapshot_ts,
        timestamp_trunc(snapshot_ts, hour)                         as obs_hour,
        num_bikes_available,
        num_docks_available,
        is_renting,
        is_returning,
        lead(snapshot_ts) over (
            partition by station_id
            order by snapshot_ts
        )                                                           as next_snapshot_ts
    from state_changes
),

with_duration as (
    select
        station_id,
        service_date,
        obs_hour,
        num_bikes_available,
        num_docks_available,
        is_renting,
        is_returning,
        -- duration until next state change, capped at 20 min to handle data gaps
        least(
            timestamp_diff(
                coalesce(next_snapshot_ts, timestamp_add(snapshot_ts, interval 10 minute)),
                snapshot_ts,
                second
            ),
            1200
        )                                                           as duration_seconds
    from with_next
)

select
    station_id,
    service_date,
    obs_hour,
    count(*)                                                        as observation_count,
    sum(duration_seconds)                                                   as total_seconds,
    -- Cap at 60 min: dense snapshots (7+ per hour due to polling jitter) can
    -- otherwise produce observed_minutes > 60, which breaks the stockout test.
    least(sum(duration_seconds) / 60.0, 60.0)                          as observed_minutes,
    safe_divide(
        sum(num_bikes_available * duration_seconds),
        sum(duration_seconds)
    )                                                               as avg_bikes_available,
    min(num_bikes_available)                                        as bikes_available_min,
    safe_divide(
        sum(num_docks_available * duration_seconds),
        sum(duration_seconds)
    )                                                               as avg_docks_available,
    least(
        sum(case when num_bikes_available = 0 then duration_seconds else 0 end) / 60.0,
        60.0
    )                                                               as stockout_minutes,
    least(
        sum(case when num_docks_available = 0 then duration_seconds else 0 end) / 60.0,
        60.0
    )                                                               as full_minutes,
    safe_divide(
        sum(case when is_renting then duration_seconds else 0 end),
        sum(duration_seconds)
    )                                                               as is_renting_ratio
from with_duration
group by station_id, service_date, obs_hour
