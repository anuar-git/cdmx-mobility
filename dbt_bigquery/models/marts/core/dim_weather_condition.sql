{{ config(materialized='table') }}

select
    condition_id,
    condition_label,
    comfort_score_min,
    comfort_score_max,
    description
from {{ ref('weather_conditions') }}
