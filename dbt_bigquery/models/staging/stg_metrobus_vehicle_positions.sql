with source as (
    select * from {{ source('raw_cdmx', 'metrobus_vehicle_positions') }}
),

flattened as (
    select
        id                                                                as entity_id,
        json_value(vehicle, '$.vehicle.id')                               as vehicle_id,
        json_value(vehicle, '$.vehicle.label')                            as vehicle_label,
        json_value(vehicle, '$.trip.route_id')                            as route_id,
        json_value(vehicle, '$.trip.trip_id')                             as trip_id,
        safe_cast(json_value(vehicle, '$.position.latitude') as float64)  as latitude,
        safe_cast(json_value(vehicle, '$.position.longitude') as float64) as longitude,
        safe_cast(json_value(vehicle, '$.position.bearing') as float64)   as bearing_deg,
        safe_cast(json_value(vehicle, '$.position.speed') as float64)     as speed_ms,
        json_value(vehicle, '$.current_status')                           as current_status,
        _snapshot_ts                                                      as snapshot_at,
        ingestion_date
    from source
    where vehicle is not null
)

select * from flattened
