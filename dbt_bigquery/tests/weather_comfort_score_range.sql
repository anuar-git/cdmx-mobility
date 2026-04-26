-- comfort_score is clamped to [0, 100] by the Spark job.
-- Any value outside this range means the clipping logic failed or Silver was
-- written with a schema mismatch (e.g. Fahrenheit temperatures fed to a
-- Celsius formula).
select obs_hour, comfort_score
from {{ ref('int_weather_city_hourly') }}
where comfort_score < 0 or comfort_score > 100
