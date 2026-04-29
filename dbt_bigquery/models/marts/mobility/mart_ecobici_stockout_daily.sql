{{
    config(
        materialized='table',
        partition_by={
            'field': 'service_date',
            'data_type': 'date',
            'granularity': 'day'
        },
        cluster_by=['station_id']
    )
}}

-- Daily EcoBici stockout and fullness summary per station.
-- Aggregates hourly stockout_minutes / full_minutes from fct_ecobici_station_hourly.
-- Used by:
--   - Pulse dashboard: top-N stressed stations (longest stockout today)
--   - Equity map:      borough-level stockout aggregation (done in frontend)

select
    e.service_date,
    e.station_id,
    e.station_key,
    s.station_name,
    s.lat,
    s.lon,
    s.capacity,
    sum(e.stockout_minutes)         as stockout_minutes,
    sum(e.full_minutes)             as full_minutes,
    sum(e.state_changes_count)      as daily_trips,
    avg(e.availability_ratio)       as avg_availability_ratio,
    avg(e.fill_ratio)               as avg_fill_ratio,
    count(distinct e.hour_ts)       as observed_hours

from {{ ref('fct_ecobici_station_hourly') }} e
inner join {{ ref('dim_station') }} s
    on e.station_key = s.station_key

group by 1, 2, 3, 4, 5, 6, 7
