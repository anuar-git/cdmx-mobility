with source as (
    select * from {{ source('raw_cdmx', 'ecobici_station_information') }}
),

stations as (
    select
        ingestion_date,
        json_value(station_el, '$.station_id')             as station_id,
        json_value(station_el, '$.name')                   as name,
        json_value(station_el, '$.short_name')             as short_name,
        cast(json_value(station_el, '$.lat') as float64)   as lat,
        cast(json_value(station_el, '$.lon') as float64)   as lon,
        cast(json_value(station_el, '$.capacity') as integer) as capacity
    from source,
        unnest(json_query_array(data, '$.stations')) as station_el
    where station_el is not null
)

select * from stations
