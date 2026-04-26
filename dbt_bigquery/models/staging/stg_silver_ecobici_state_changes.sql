with source as (
    select * from {{ source('silver_cdmx', 'ecobici_state_changes') }}
)

select
    snapshot_ts,
    station_id,
    num_bikes_available,
    num_docks_available,
    is_renting  = 1 as is_renting,
    is_returning = 1 as is_returning,
    service_date
from source
