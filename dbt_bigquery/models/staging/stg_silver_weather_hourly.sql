-- The Spark job pivots to one row per UTC hour (wide format). There is no
-- coordinate_id column in Silver — per-coordinate columns are named
-- {coordinate_id}_{metric} (e.g. centro_temperature_2m). This model exposes
-- only the city-wide avg_* columns and derived features for downstream use.
with source as (
    select * from {{ source('silver_cdmx', 'weather_hourly_fact') }}
)

select
    timestamp_trunc(obs_timestamp, hour)    as obs_hour,
    avg_temperature_2m,
    avg_precipitation,
    avg_windspeed_10m,
    avg_relativehumidity_2m,
    heat_index,
    comfort_score,
    wind_category,
    precipitation_flag,
    service_date
from source
