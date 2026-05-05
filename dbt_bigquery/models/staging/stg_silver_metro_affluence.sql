with source as (
    select * from {{ source('silver_cdmx', 'metro_affluence') }}
)

select
    service_date,
    linea,
    station_canonical,
    daily_entries
from source
qualify row_number() over (
    partition by service_date, linea, station_canonical
    order by daily_entries desc
) = 1
