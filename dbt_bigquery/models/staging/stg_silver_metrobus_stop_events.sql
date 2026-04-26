with source as (
    select * from {{ source('silver_cdmx', 'metrobus_stop_events') }}
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
    dwell_seconds / 60.0            as dwell_minutes,
    service_date
from source
