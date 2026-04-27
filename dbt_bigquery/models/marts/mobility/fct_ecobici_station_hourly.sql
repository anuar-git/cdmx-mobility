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

-- Deduplicate on (station_id, obs_hour): the intermediate groups by service_date too,
-- so a station near the CDMX midnight boundary can produce two rows for the same
-- obs_hour in different service_date partitions. Keep the later service_date.
deduped as (
    select *
    from agg
    qualify row_number() over (
        partition by station_id, obs_hour
        order by service_date desc
    ) = 1
),

stations as (
    select station_id, station_key, capacity
    from {{ ref('dim_station') }}
    where mode = 'ecobici'
)

select
    {{ dbt_utils.generate_surrogate_key(['deduped.station_id', 'cast(deduped.obs_hour as string)']) }}
                                                                    as fct_sk,
    deduped.station_id,
    stations.station_key,
    deduped.obs_hour                                                as hour_ts,
    deduped.service_date,
    stations.capacity,
    deduped.avg_bikes_available                                     as bikes_available_avg,
    deduped.bikes_available_min,
    deduped.avg_docks_available                                     as docks_available_avg,
    deduped.stockout_minutes,
    deduped.full_minutes,
    deduped.observation_count                                       as state_changes_count,
    deduped.observed_minutes,
    deduped.is_renting_ratio                                        as availability_ratio,
    safe_divide(deduped.avg_bikes_available, stations.capacity)     as fill_ratio
from deduped
left join stations using (station_id)
