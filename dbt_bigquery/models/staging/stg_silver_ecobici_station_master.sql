with source as (
    select * from {{ source('silver_cdmx', 'ecobici_station_master') }}
)

select
    station_id,
    name,
    lat,
    lon,
    capacity,
    st_geogpoint(lon, lat) as geog
from source
