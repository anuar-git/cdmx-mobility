{{ config(materialized='ephemeral') }}

-- Silver weather is already wide-format: one row per UTC hour with city-wide
-- avg_* columns pre-computed by the Spark job across four CDMX coordinates.
-- This model renames columns to human-friendly aliases, normalises the boolean
-- precipitation_flag, and adds a composite is_adverse_weather flag used by the
-- unified fact table and dim_weather_condition.

with source as (
    select * from {{ ref('stg_silver_weather_hourly') }}
)

select
    obs_hour,
    service_date,
    avg_temperature_2m                                              as temperature_c,
    avg_relativehumidity_2m                                         as humidity_pct,
    avg_precipitation                                               as precipitation_mm,
    avg_windspeed_10m                                               as windspeed_ms,
    heat_index,
    comfort_score,
    wind_category,
    -- precipitation_flag comes from Spark as boolean; coalesce guards NULL rows
    coalesce(precipitation_flag, false)                             as is_rainy,
    -- adverse = raining, or heat index >= 35 °C, or strong wind (Beaufort 6+)
    -- wind_category is STRING: 'calm' | 'breeze' | 'strong' (see bronze_to_silver_weather.py)
    coalesce(precipitation_flag, false)
        or avg_temperature_2m >= 35
        or wind_category = 'strong'                                 as is_adverse_weather
from source
