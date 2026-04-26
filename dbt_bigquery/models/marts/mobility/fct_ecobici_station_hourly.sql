{{
    config(
        materialized='incremental',
        unique_key=['station_id', 'hour_ts'],
        partition_by={'field': 'service_date', 'data_type': 'date'},
        cluster_by=['station_id'],
        incremental_strategy='merge',
        on_schema_change='append_new_columns'
    )
}}

-- Partitioned by service_date, clustered by station_id.
-- Incremental merge re-processes the last 3 days to absorb late-arriving Silver
-- data or Silver re-runs. For full backfill, use: dbt run --full-refresh.

with agg as (
    select *
    from {{ ref('int_ecobici_station_hourly_agg') }}
    {% if is_incremental() %}
    where service_date >= date_sub(current_date('America/Mexico_City'), interval 3 day)
    {% endif %}
),

stations as (
    select station_id, station_key, capacity
    from {{ ref('dim_station') }}
    where mode = 'ecobici'
)

select
    {{ dbt_utils.generate_surrogate_key(['agg.station_id', 'cast(agg.obs_hour as string)']) }}
                                                                    as fct_sk,
    agg.station_id,
    stations.station_key,
    agg.obs_hour                                                    as hour_ts,
    agg.service_date,
    stations.capacity,
    agg.avg_bikes_available                                         as bikes_available_avg,
    agg.bikes_available_min,
    agg.avg_docks_available                                         as docks_available_avg,
    agg.stockout_minutes,
    agg.full_minutes,
    agg.observation_count                                           as state_changes_count,
    agg.observed_minutes,
    agg.is_renting_ratio                                            as availability_ratio,
    safe_divide(agg.avg_bikes_available, stations.capacity)         as fill_ratio
from agg
left join stations using (station_id)
