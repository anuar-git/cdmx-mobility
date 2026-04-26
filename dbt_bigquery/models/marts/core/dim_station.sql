{{ config(materialized='table') }}

with ecobici_current as (
    select *
    from {{ ref('ecobici_station_snapshot') }}
    where dbt_valid_to is null
),

metro as (
    select * from {{ ref('metro_station_locations') }}
),

metrobus_latest as (
    -- deduplicate to most-recent static GTFS ingest; physical stops only
    select *
    from {{ ref('stg_metrobus_stops') }}
    where location_type = 0
    qualify row_number() over (
        partition by stop_id
        order by ingestion_date desc
    ) = 1
),

ecobici_dim as (
    select
        {{ dbt_utils.generate_surrogate_key(["'ecobici'", 'station_id']) }}  as station_key,
        station_id                                                             as station_id,
        name                                                                   as station_name,
        short_name                                                             as station_short_name,
        'ecobici'                                                              as mode,
        lat,
        lon,
        st_geogpoint(lon, lat)                                                 as geog,
        capacity,
        cast(null as string)                                                   as linea,
        cast(null as string)                                                   as borough,
        cast(null as string)                                                   as colonia,
        cast(null as date)                                                     as opened_date,
        cast(null as string)                                                   as parent_station_id
    from ecobici_current
),

metro_dim as (
    select
        {{ dbt_utils.generate_surrogate_key(["'metro'", 'station_canonical', 'linea']) }}  as station_key,
        station_canonical                                                                    as station_id,
        station_canonical                                                                    as station_name,
        cast(null as string)                                                                 as station_short_name,
        'metro'                                                                              as mode,
        lat,
        lon,
        st_geogpoint(lon, lat)                                                               as geog,
        cast(null as integer)                                                                as capacity,
        linea,
        borough,
        colonia,
        opened_date,
        cast(null as string)                                                                 as parent_station_id
    from metro
),

metrobus_dim as (
    select
        {{ dbt_utils.generate_surrogate_key(["'metrobus'", 'stop_id']) }}  as station_key,
        stop_id                                                               as station_id,
        stop_name                                                             as station_name,
        stop_code                                                             as station_short_name,
        'metrobus'                                                            as mode,
        latitude                                                              as lat,
        longitude                                                             as lon,
        st_geogpoint(longitude, latitude)                                     as geog,
        cast(null as integer)                                                 as capacity,
        cast(null as string)                                                  as linea,
        cast(null as string)                                                  as borough,
        cast(null as string)                                                  as colonia,
        cast(null as date)                                                    as opened_date,
        parent_station                                                        as parent_station_id
    from metrobus_latest
)

select * from ecobici_dim
union all
select * from metro_dim
union all
select * from metrobus_dim
