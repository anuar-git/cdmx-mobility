"""Station deep-dive endpoints — list, hourly demand, weather scatter, neighbors, forecast."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Path, Query
from google.cloud import bigquery

router = APIRouter(prefix="/api/station")

_PROJECT = os.getenv("CDMX_GCP_PROJECT_ID", "cdmx-mobility-prod")


@lru_cache(maxsize=1)
def _bq() -> bigquery.Client:
    return bigquery.Client(project=_PROJECT)


def _q(sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in _bq().query(sql).result()]


def _q_params(sql: str, params: list[bigquery.ScalarQueryParameter]) -> list[dict[str, Any]]:
    cfg = bigquery.QueryJobConfig(query_parameters=params)
    return [dict(row) for row in _bq().query(sql, job_config=cfg).result()]


@router.get("/list")
def station_list() -> list[dict]:
    """All stations with lat/lon, mode, and name — used to populate the map base layer
    and the station-picker dropdown."""
    sql = f"""
        SELECT
            station_id,
            station_key,
            station_name,
            mode,
            lat,
            lon,
            capacity,
            linea,
            borough
        FROM `{_PROJECT}.marts_cdmx.dim_station`
        WHERE lat IS NOT NULL AND lon IS NOT NULL
        ORDER BY mode, station_name
    """
    return _q(sql)


@router.get("/{station_id}/hourly")
def station_hourly(
    station_id: str = Path(description="EcoBici station_id"),
    days: int = Query(default=30, ge=1, le=90),
) -> list[dict]:
    """Hourly demand time-series for an EcoBici station over the past N days."""
    sql = """
        SELECT
            CAST(hour_ts AS STRING)         AS hour_ts,
            CAST(service_date AS STRING)    AS service_date,
            state_changes_count             AS hourly_trips,
            bikes_available_avg,
            docks_available_avg,
            stockout_minutes,
            availability_ratio
        FROM `@project.marts_cdmx.fct_ecobici_station_hourly`
        WHERE station_id = @station_id
          AND service_date >= DATE_SUB(CURRENT_DATE('America/Mexico_City'), INTERVAL @days DAY)
        ORDER BY hour_ts
    """.replace("@project", _PROJECT)
    return _q_params(
        sql,
        [
            bigquery.ScalarQueryParameter("station_id", "STRING", station_id),
            bigquery.ScalarQueryParameter("days", "INT64", days),
        ],
    )


@router.get("/{station_id}/weather-scatter")
def station_weather_scatter(
    station_id: str = Path(description="EcoBici station_id"),
) -> list[dict]:
    """Daily (temperature, trips) pairs for weather sensitivity scatter chart."""
    sql = """
        SELECT
            CAST(service_date AS STRING)    AS service_date,
            daily_trips,
            avg_temperature_c,
            avg_humidity_pct,
            avg_precipitation_mm,
            was_rainy,
            was_adverse_weather
        FROM `@project.marts_cdmx.mart_station_weather_sensitivity`
        WHERE station_id = @station_id
        ORDER BY service_date
    """.replace("@project", _PROJECT)
    return _q_params(
        sql,
        [
            bigquery.ScalarQueryParameter("station_id", "STRING", station_id),
        ],
    )


@router.get("/{station_id}/neighbors")
def station_neighbors(
    station_id: str = Path(description="Any station_id"),
    radius_m: int = Query(default=500, ge=100, le=2000),
) -> list[dict]:
    """Stations within radius_m metres, across all modes."""
    sql = """
        SELECT
            n.station_id,
            n.station_name,
            n.mode,
            n.lat,
            n.lon,
            ROUND(ST_DISTANCE(s.geog, n.geog), 0)  AS distance_m
        FROM `@project.marts_cdmx.dim_station` s
        JOIN `@project.marts_cdmx.dim_station` n
            ON  n.station_key != s.station_key
            AND n.geog IS NOT NULL
            AND ST_DISTANCE(s.geog, n.geog) <= @radius_m
        WHERE s.station_id = @station_id
          AND s.geog IS NOT NULL
        ORDER BY distance_m
        LIMIT 20
    """.replace("@project", _PROJECT)
    return _q_params(
        sql,
        [
            bigquery.ScalarQueryParameter("station_id", "STRING", station_id),
            bigquery.ScalarQueryParameter("radius_m", "INT64", radius_m),
        ],
    )


@router.get("/{station_id}/forecast")
def station_forecast(
    station_id: str = Path(description="EcoBici station_id"),
) -> list[dict]:
    """24-hour ahead forecast using 7-day same-hour average as the baseline.

    Returns 24 rows: one per hour 0-23, with avg_trips and stddev_trips
    computed from the past 28 days (4 weeks of same-hour observations).
    """
    sql = """
        WITH history AS (
            SELECT
                EXTRACT(HOUR FROM hour_ts AT TIME ZONE 'America/Mexico_City')   AS hour_of_day,
                state_changes_count                                              AS trips
            FROM `@project.marts_cdmx.fct_ecobici_station_hourly`
            WHERE station_id = @station_id
              AND service_date >= DATE_SUB(CURRENT_DATE('America/Mexico_City'), INTERVAL 28 DAY)
        )
        SELECT
            hour_of_day,
            ROUND(AVG(trips), 1)    AS forecast_trips,
            ROUND(STDDEV(trips), 1) AS stddev_trips,
            COUNT(*)                AS sample_hours
        FROM history
        GROUP BY hour_of_day
        ORDER BY hour_of_day
    """.replace("@project", _PROJECT)
    return _q_params(
        sql,
        [
            bigquery.ScalarQueryParameter("station_id", "STRING", station_id),
        ],
    )
