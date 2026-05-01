"""Executive pulse endpoints — today's ridership, EcoBici stockout, weather."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Query
from google.cloud import bigquery

router = APIRouter(prefix="/api/pulse")

_PROJECT = os.getenv("CDMX_GCP_PROJECT_ID", "cdmx-mobility-prod")


@lru_cache(maxsize=1)
def _bq() -> bigquery.Client:
    return bigquery.Client(project=_PROJECT)


def _q(sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in _bq().query(sql).result()]


@router.get("/ridership")
def pulse_ridership(days: int = Query(default=8, ge=2, le=30)) -> list[dict]:
    """Daily ridership per mode for the past N days.

    Returns one row per (service_date, mode). Metro comes from
    fct_metro_affluence_daily (entries), Metrobús from fct_metrobus_stop_events
    (dwell events as a proxy for boardings), EcoBici from mart_ecobici_stockout_daily
    (state_changes_count = bike pick-ups + drop-offs).
    """
    sql = f"""
        WITH metro AS (
            SELECT
                CAST(service_date AS STRING)    AS service_date,
                'metro'                         AS mode,
                SUM(daily_entries)              AS ridership
            FROM `{_PROJECT}.marts_cdmx.fct_metro_affluence_daily`
            WHERE service_date >= DATE_SUB(CURRENT_DATE('America/Mexico_City'), INTERVAL {days} DAY)
            GROUP BY 1, 2
        ),
        metrobus AS (
            SELECT
                CAST(service_date AS STRING)    AS service_date,
                'metrobus'                      AS mode,
                COUNT(*)                        AS ridership
            FROM `{_PROJECT}.marts_cdmx.fct_metrobus_stop_events`
            WHERE service_date >= DATE_SUB(CURRENT_DATE('America/Mexico_City'), INTERVAL {days} DAY)
            GROUP BY 1, 2
        ),
        ecobici AS (
            SELECT
                CAST(service_date AS STRING)    AS service_date,
                'ecobici'                       AS mode,
                SUM(daily_trips)                AS ridership
            FROM `{_PROJECT}.marts_cdmx.mart_ecobici_stockout_daily`
            WHERE service_date >= DATE_SUB(CURRENT_DATE('America/Mexico_City'), INTERVAL {days} DAY)
            GROUP BY 1, 2
        )
        SELECT * FROM metro
        UNION ALL SELECT * FROM metrobus
        UNION ALL SELECT * FROM ecobici
        ORDER BY service_date DESC, mode
    """
    return _q(sql)


@router.get("/stockout")
def pulse_stockout(
    date: str | None = Query(default=None, description="YYYY-MM-DD; defaults to today"),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[dict]:
    """Top N EcoBici stations ranked by stockout_minutes for a given date.

    Includes lat/lon for the Deck.gl ScatterplotLayer — radius scaled by
    stockout_minutes, color by availability_ratio.
    """
    if date:
        date_expr = f"DATE '{date}'"
    else:
        date_expr = (
            f"(SELECT MAX(service_date) FROM `{_PROJECT}.marts_cdmx.mart_ecobici_stockout_daily`)"
        )
    sql = f"""
        SELECT
            station_id,
            station_name,
            lat,
            lon,
            stockout_minutes,
            full_minutes,
            daily_trips,
            ROUND(avg_availability_ratio, 3)    AS avg_availability_ratio,
            capacity
        FROM `{_PROJECT}.marts_cdmx.mart_ecobici_stockout_daily`
        WHERE service_date = {date_expr}
        ORDER BY stockout_minutes DESC
        LIMIT {limit}
    """
    return _q(sql)


@router.get("/weather")
def pulse_weather() -> dict:
    """Latest city-wide weather observation (most recent hour in fct_unified_mobility_hourly)."""
    sql = f"""
        SELECT
            CAST(hour_ts AS STRING)         AS hour_ts,
            CAST(service_date AS STRING)    AS service_date,
            temperature_c,
            humidity_pct,
            precipitation_mm,
            windspeed_ms,
            comfort_score,
            weather_condition,
            is_rainy,
            is_adverse_weather
        FROM `{_PROJECT}.marts_cdmx.fct_unified_mobility_hourly`
        WHERE mode = 'ecobici'
          AND temperature_c IS NOT NULL
        ORDER BY hour_ts DESC
        LIMIT 1
    """
    rows = _q(sql)
    return rows[0] if rows else {}
