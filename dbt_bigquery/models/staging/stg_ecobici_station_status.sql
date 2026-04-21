with source as (
    select * from {{ source('raw_cdmx', 'ecobici_station_status') }}
),

stations as (
    select
        ingestion_ts,
        timestamp_seconds(last_updated)                                          as feed_updated_at,
        json_value(station_el, '$.station_id')                                   as station_id,
        cast(json_value(station_el, '$.num_bikes_available') as integer)         as bikes_available,
        cast(json_value(station_el, '$.num_docks_available') as integer)         as docks_available,
        cast(json_value(station_el, '$.num_bikes_disabled') as integer)          as bikes_disabled,
        cast(json_value(station_el, '$.num_docks_disabled') as integer)          as docks_disabled,
        json_value(station_el, '$.is_renting') = '1'                             as is_renting,
        json_value(station_el, '$.is_returning') = '1'                           as is_returning,
        json_value(station_el, '$.is_installed') = '1'                           as is_installed,
        timestamp_seconds(
            cast(json_value(station_el, '$.last_reported') as integer)
        )                                                                         as station_last_reported_at
    from source,
        unnest(json_query_array(data, '$.stations')) as station_el
    where station_el is not null
)

select * from stations
