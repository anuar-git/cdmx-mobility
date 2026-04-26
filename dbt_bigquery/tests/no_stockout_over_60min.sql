-- Canary: no station should show more than 60 stockout minutes in a single hour.
-- More than 60 minutes in a 60-minute window means the 20-minute observation cap
-- is being applied incorrectly or Silver data contains duplicate records.
select station_id, hour_ts, stockout_minutes
from {{ ref('fct_ecobici_station_hourly') }}
where stockout_minutes > 60
