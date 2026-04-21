with source as (
    select * from {{ source('raw_cdmx', 'metro_affluence') }}
),

renamed as (
    select
        cast(fecha as date)        as date,
        trim(linea)                as line,
        trim(estacion)             as station,
        cast(afluencia as integer) as entries,
        ingestion_date
    from source
    where afluencia is not null
)

select * from renamed
