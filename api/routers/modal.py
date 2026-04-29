"""Modal substitution endpoints — Metro line ridership and nearby alternative modes."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Query
from google.cloud import bigquery

router = APIRouter(prefix="/api/modal")

_PROJECT = os.getenv("CDMX_GCP_PROJECT_ID", "cdmx-mobility-prod")


@lru_cache(maxsize=1)
def _bq() -> bigquery.Client:
    return bigquery.Client(project=_PROJECT)


def _q(sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in _bq().query(sql).result()]


def _q_params(sql: str, params: list[bigquery.ScalarQueryParameter]) -> list[dict[str, Any]]:
    cfg = bigquery.QueryJobConfig(query_parameters=params)
    return [dict(row) for row in _bq().query(sql, job_config=cfg).result()]


@router.get("/lines")
def modal_lines() -> list[dict]:
    """All Metro lines with their 30-day average daily ridership and trend.

    Used to populate the line selector in Dashboard 3.
    """
    sql = f"""
        SELECT
            metro_line,
            COUNT(DISTINCT service_date)                    AS days_with_data,
            ROUND(AVG(metro_daily_entries), 0)              AS avg_daily_ridership,
            ROUND(AVG(nearby_metrobus_events), 0)           AS avg_nearby_metrobus_events,
            ROUND(AVG(nearby_ecobici_trips), 0)             AS avg_nearby_ecobici_trips,
            COUNTIF(is_low_service_day)                     AS low_service_days
        FROM `{_PROJECT}.marts_cdmx.mart_modal_substitution`
        WHERE service_date >= DATE_SUB(CURRENT_DATE('America/Mexico_City'), INTERVAL 30 DAY)
        GROUP BY metro_line
        ORDER BY avg_daily_ridership DESC
    """
    return _q(sql)


@router.get("/substitution")
def modal_substitution(
    line: str = Query(description="Metro line identifier, e.g. 'Línea 1' or 'A'"),
    days: int = Query(default=90, ge=7, le=365),
) -> list[dict]:
    """Time-series of Metro ridership vs. nearby Metrobús and EcoBici activity.

    Used for the dual-axis chart in Dashboard 3 showing the substitution signal.
    """
    sql = """
        SELECT
            CAST(service_date AS STRING)            AS service_date,
            metro_daily_entries,
            ROUND(metro_7d_avg, 0)                  AS metro_7d_avg,
            ROUND(metro_vs_avg_ratio, 3)            AS metro_vs_avg_ratio,
            is_low_service_day,
            nearby_metrobus_events,
            nearby_metrobus_vehicles,
            nearby_ecobici_trips,
            ROUND(nearby_ecobici_availability, 3)   AS nearby_ecobici_availability
        FROM `@project.marts_cdmx.mart_modal_substitution`
        WHERE metro_line = @line
          AND service_date >= DATE_SUB(CURRENT_DATE('America/Mexico_City'), INTERVAL @days DAY)
        ORDER BY service_date
    """.replace("@project", _PROJECT)
    return _q_params(
        sql,
        [
            bigquery.ScalarQueryParameter("line", "STRING", line),
            bigquery.ScalarQueryParameter("days", "INT64", days),
        ],
    )


@router.get("/corridor")
def modal_corridor(
    line: str = Query(description="Metro line identifier"),
) -> list[dict]:
    """All stations (Metro + nearby Metrobús + EcoBici) in a line's 300 m corridor.

    Used to populate the Deck.gl map layers in Dashboard 3: Metro stops,
    alternative-mode stations, and ArcLayer connections.
    """
    sql = """
        WITH metro_stops AS (
            SELECT station_id, station_name, 'metro' AS mode, lat, lon, linea AS line_label, geog
            FROM `@project.marts_cdmx.dim_station`
            WHERE mode = 'metro' AND linea = @line AND geog IS NOT NULL
        ),
        nearby AS (
            SELECT
                n.station_id,
                n.station_name,
                n.mode,
                n.lat,
                n.lon,
                CAST(NULL AS STRING)                        AS line_label,
                ROUND(ST_DISTANCE(m.geog, n.geog), 0)      AS distance_m
            FROM metro_stops m
            JOIN `@project.marts_cdmx.dim_station` n
                ON  n.mode IN ('metrobus', 'ecobici')
                AND n.geog IS NOT NULL
                AND ABS(m.lat - n.lat) < 0.003
                AND ABS(m.lon - n.lon) < 0.003
                AND ST_DISTANCE(m.geog, n.geog) <= 300
        )
        SELECT station_id, station_name, mode, lat, lon, line_label,
               CAST(NULL AS FLOAT64) AS distance_m
        FROM metro_stops
        UNION ALL
        SELECT station_id, station_name, mode, lat, lon, line_label, distance_m
        FROM nearby
        QUALIFY ROW_NUMBER() OVER (PARTITION BY station_id, mode ORDER BY distance_m) = 1
        ORDER BY mode, station_name
    """.replace("@project", _PROJECT)
    return _q_params(
        sql,
        [
            bigquery.ScalarQueryParameter("line", "STRING", line),
        ],
    )
