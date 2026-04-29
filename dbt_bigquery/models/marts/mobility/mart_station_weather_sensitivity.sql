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

-- Daily EcoBici demand paired with weather observations, per station.
-- Daily grain (not hourly) makes the scatter chart readable: one point per
-- station per day plotting temperature vs. total trips.
--
-- Weather comes from fct_unified_mobility_hourly (ecobici mode rows already
-- have the city-wide hourly weather joined in).
--
-- Rows with zero trips are excluded — they represent hours with no data rather
-- than genuinely zero activity and would skew the weather sensitivity fit.

select
    e.service_date,
    e.station_id,
    e.station_key,
    s.station_name,
    s.lat,
    s.lon,
    sum(e.state_changes_count)          as daily_trips,
    avg(e.availability_ratio)           as avg_availability_ratio,
    -- Weather aggregated from hourly observations across the day
    round(avg(u.temperature_c), 1)      as avg_temperature_c,
    round(avg(u.humidity_pct), 1)       as avg_humidity_pct,
    round(avg(u.precipitation_mm), 2)   as avg_precipitation_mm,
    round(avg(u.windspeed_ms), 2)       as avg_windspeed_ms,
    max(cast(u.is_rainy as int64))           = 1 as was_rainy,
    max(cast(u.is_adverse_weather as int64)) = 1 as was_adverse_weather

from {{ ref('fct_ecobici_station_hourly') }} e
inner join {{ ref('dim_station') }} s
    on e.station_key = s.station_key
inner join {{ ref('fct_unified_mobility_hourly') }} u
    on  u.station_id   = e.station_id
    and u.service_date = e.service_date
    and u.hour_ts      = e.hour_ts
    and u.mode         = 'ecobici'

where e.state_changes_count > 0

group by 1, 2, 3, 4, 5, 6
