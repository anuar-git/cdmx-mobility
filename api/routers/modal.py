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
        WHERE service_date >= DATE_SUB(CURRENT_DATE('America/Mexico_City'), INTERVAL 365 DAY)
        GROUP BY metro_line
        ORDER BY avg_daily_ridership DESC
    """
    return _q(sql)


@router.get("/substitution")
def modal_substitution(
    line: str = Query(description="Metro line identifier, e.g. 'Línea 1' or 'A'"),
    days: int = Query(default=365, ge=7, le=730),
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
        WHERE REPLACE(metro_line, 'í', 'i') = REPLACE(@line, 'í', 'i')
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
            SELECT station_id, station_name, 'metro' AS mode, lat, lon, linea AS line_label,
                   CAST(NULL AS FLOAT64) AS distance_m, station_key, geog
            FROM `@project.marts_cdmx.dim_station`
            WHERE mode = 'metro'
              AND REPLACE(linea, 'í', 'i') = REPLACE(@line, 'í', 'i')
              AND geog IS NOT NULL
        ),
        nearby AS (
            SELECT
                n.station_id,
                n.station_name,
                n.mode,
                n.lat,
                n.lon,
                CAST(NULL AS STRING)                        AS line_label,
                ROUND(ST_DISTANCE(m.geog, n.geog), 0)      AS distance_m,
                n.station_key,
                n.geog
            FROM metro_stops m
            JOIN `@project.marts_cdmx.dim_station` n
                ON  n.mode IN ('metrobus', 'ecobici')
                AND n.geog IS NOT NULL
                AND ABS(m.lat - n.lat) < 0.003
                AND ABS(m.lon - n.lon) < 0.003
                AND ST_DISTANCE(m.geog, n.geog) <= 300
        ),
        combined AS (
            SELECT station_id, station_name, mode, lat, lon, line_label, distance_m, station_key
            FROM metro_stops
            UNION ALL
            SELECT station_id, station_name, mode, lat, lon, line_label, distance_m, station_key
            FROM nearby
            QUALIFY ROW_NUMBER() OVER (PARTITION BY station_id, mode ORDER BY distance_m) = 1
        ),
        metro_entries AS (
            SELECT station_canonical, daily_entries, CAST(service_date AS STRING) AS latest_date
            FROM `@project.marts_cdmx.fct_metro_affluence_daily`
            WHERE REPLACE(linea, 'í', 'i') = REPLACE(@line, 'í', 'i')
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY station_canonical
                ORDER BY service_date DESC, daily_entries DESC
            ) = 1
        ),
        ecobici_now AS (
            SELECT
                station_id,
                ROUND(bikes_available_avg, 0)               AS bikes_available,
                ROUND(availability_ratio * 100, 0)          AS availability_pct
            FROM `@project.marts_cdmx.fct_ecobici_station_hourly`
            WHERE service_date >= DATE_SUB(CURRENT_DATE('America/Mexico_City'), INTERVAL 3 DAY)
            QUALIFY ROW_NUMBER() OVER (PARTITION BY station_id ORDER BY hour_ts DESC) = 1
        ),
        metrobus_stats AS (
            SELECT
                station_key,
                ROUND(AVG(headway_minutes), 1)                              AS avg_headway_min,
                STRING_AGG(DISTINCT route_short_name ORDER BY route_short_name LIMIT 4) AS routes
            FROM `@project.marts_cdmx.fct_metrobus_stop_events`
            WHERE service_date >= DATE_SUB(CURRENT_DATE('America/Mexico_City'), INTERVAL 30 DAY)
              AND headway_minutes IS NOT NULL
              AND route_short_name IS NOT NULL
            GROUP BY station_key
        )
        SELECT
            c.station_id,
            c.station_name,
            c.mode,
            c.lat,
            c.lon,
            c.line_label,
            c.distance_m,
            me.daily_entries                AS metro_daily_entries,
            me.latest_date                  AS metro_latest_date,
            eb.bikes_available              AS ecobici_bikes_available,
            eb.availability_pct             AS ecobici_availability_pct,
            mb.avg_headway_min              AS metrobus_avg_headway_min,
            mb.routes                       AS metrobus_routes
        FROM combined c
        LEFT JOIN metro_entries me
               ON c.mode = 'metro'    AND c.station_id = me.station_canonical
        LEFT JOIN ecobici_now eb
               ON c.mode = 'ecobici'  AND c.station_id = eb.station_id
        LEFT JOIN metrobus_stats mb
               ON c.mode = 'metrobus' AND c.station_key = mb.station_key
        ORDER BY c.mode, c.station_name
    """.replace("@project", _PROJECT)
    return _q_params(
        sql,
        [
            bigquery.ScalarQueryParameter("line", "STRING", line),
        ],
    )
