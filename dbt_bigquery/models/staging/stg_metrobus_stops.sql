with source as (
    select * from {{ source('raw_cdmx', 'metrobus_stops') }}
),

renamed as (
    select
        trim(stop_id)                                as stop_id,
        nullif(trim(stop_code), '')                  as stop_code,
        trim(stop_name)                              as stop_name,
        cast(stop_lat as float64)                    as latitude,
        cast(stop_lon as float64)                    as longitude,
        coalesce(location_type, 0)                   as location_type,
        nullif(trim(coalesce(parent_station, '')), '') as parent_station,
        ingestion_date
    from source
    where stop_id is not null
)

select * from renamed
