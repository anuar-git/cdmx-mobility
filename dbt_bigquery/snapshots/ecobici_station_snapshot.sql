{% snapshot ecobici_station_snapshot %}

{{
    config(
        unique_key='station_id',
        strategy='check',
        check_cols=['name', 'lat', 'lon', 'capacity'],
        invalidate_hard_deletes=True
    )
}}

select
    station_id,
    name,
    short_name,
    lat,
    lon,
    capacity,
    ingestion_date
from {{ ref('stg_ecobici_station_information') }}

{% endsnapshot %}
