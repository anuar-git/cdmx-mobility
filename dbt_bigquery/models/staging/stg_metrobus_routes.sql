with source as (
    select * from {{ source('raw_cdmx', 'metrobus_routes') }}
),

renamed as (
    select
        trim(route_id)                                   as route_id,
        nullif(trim(coalesce(agency_id, '')), '')        as agency_id,
        trim(route_short_name)                           as route_short_name,
        trim(route_long_name)                            as route_long_name,
        route_type,
        nullif(trim(coalesce(route_color, '')), '')      as route_color,
        nullif(trim(coalesce(route_text_color, '')), '') as route_text_color,
        ingestion_date
    from source
    where route_id is not null
)

select * from renamed
