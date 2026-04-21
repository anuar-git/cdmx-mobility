with status as (
    select * from {{ ref('stg_ecobici_station_status') }}
),

info as (
    select * from {{ ref('stg_ecobici_station_information') }}
),

-- Use only the most recent daily snapshot per station to avoid fan-out on the join
latest_info as (
    select * except (rn)
    from (
        select
            info.*,
            row_number() over (partition by info.station_id order by info.ingestion_date desc) as rn
        from info
    )
    where rn = 1
)

select
    status.ingestion_ts,
    status.feed_updated_at,
    status.station_id,
    latest_info.name              as station_name,
    latest_info.short_name,
    latest_info.lat,
    latest_info.lon,
    latest_info.capacity,
    status.bikes_available,
    status.docks_available,
    status.bikes_disabled,
    status.docks_disabled,
    status.is_renting,
    status.is_returning,
    status.is_installed,
    status.station_last_reported_at,
    safe_divide(
        status.bikes_available,
        nullif(latest_info.capacity, 0)
    )                             as availability_ratio
from status
left join latest_info using (station_id)
