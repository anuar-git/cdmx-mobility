with source as (
    select * from {{ source('silver_cdmx', 'metro_affluence') }}
)

select
    service_date,
    linea,
    station_canonical,
    daily_entries
from source
