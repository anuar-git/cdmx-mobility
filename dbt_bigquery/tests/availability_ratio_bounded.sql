-- availability_ratio is a time-weighted fraction in [0, 1].
-- Values outside this range indicate a SAFE_DIVIDE edge case or bad duration weights.
select station_id, hour_ts, availability_ratio
from {{ ref('fct_ecobici_station_hourly') }}
where availability_ratio < 0 or availability_ratio > 1
