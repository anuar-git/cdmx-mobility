{{
    config(
        materialized='table',
        partition_by={'field': 'service_date', 'data_type': 'date', 'granularity': 'month'},
        cluster_by=['linea', 'station_canonical']
    )
}}

-- Source: Silver metro affluence (afluenciastc_simple CSV).
-- Silver has no tipo_pago breakdown — each (service_date, linea, station_canonical)
-- is already a single daily total. The planned window-sum across tipo_pago does not
-- apply; daily_entries is the complete daily count for that station-line pair.

with silver as (
    select service_date, linea, station_canonical, daily_entries
    from {{ ref('stg_silver_metro_affluence') }}
    qualify row_number() over (
        partition by service_date, linea, station_canonical
        order by daily_entries desc
    ) = 1
),

dim_sta as (
    select station_id, linea, station_key, borough, colonia
    from {{ ref('dim_station') }}
    where mode = 'metro'
),

dim_dt as (
    select
        date_day,
        day_name,
        is_weekend,
        is_weekday,
        is_public_holiday,
        is_bridge_day,
        is_quincena_payday,
        is_school_vacation,
        holiday_name
    from {{ ref('dim_date') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['silver.service_date', 'silver.station_canonical', 'silver.linea']) }}
                                                                   as fct_sk,
    silver.service_date,
    silver.linea,
    silver.station_canonical,
    silver.daily_entries,
    dim_sta.station_key,
    dim_sta.borough,
    dim_sta.colonia,
    dim_dt.day_name,
    dim_dt.is_weekend,
    dim_dt.is_weekday,
    dim_dt.is_public_holiday,
    dim_dt.is_bridge_day,
    dim_dt.is_quincena_payday,
    dim_dt.is_school_vacation,
    dim_dt.holiday_name
from silver
left join dim_sta
    on  dim_sta.station_id = silver.station_canonical
    and dim_sta.linea      = silver.linea
left join dim_dt on dim_dt.date_day = silver.service_date
