"""Equity & access endpoints — station-level accessibility scores for the choropleth map."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Query
from google.cloud import bigquery

router = APIRouter(prefix="/api/equity")

_PROJECT = os.getenv("CDMX_GCP_PROJECT_ID", "cdmx-mobility-prod")


@lru_cache(maxsize=1)
def _bq() -> bigquery.Client:
    return bigquery.Client(project=_PROJECT)


def _q(sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in _bq().query(sql).result()]


@router.get("/scores")
def equity_scores() -> list[dict]:
    """Transit accessibility score for every station (all modes).

    The frontend groups these into alcaldías using Turf.js booleanPointInPolygon
    against dashboard/public/alcaldias.geojson, then aggregates to borough-level
    averages for the choropleth fill colour.

    borough is populated only for Metro stations (from dim_station); the frontend
    uses spatial point-in-polygon for EcoBici and Metrobús stations.
    """
    sql = f"""
        SELECT
            station_id,
            station_name,
            mode,
            lat,
            lon,
            accessibility_score,
            nearby_mode_count,
            nearby_metro_count,
            nearby_metrobus_count,
            nearby_ecobici_count
        FROM `{_PROJECT}.marts_cdmx.mart_accessibility_score`
        WHERE lat IS NOT NULL AND lon IS NOT NULL
        ORDER BY accessibility_score DESC
    """
    return _q(sql)


@router.get("/stockout-by-borough")
def equity_stockout(
    days: int = Query(default=30, ge=1, le=90),
) -> list[dict]:
    """Average daily stockout minutes per EcoBici station for the past N days.

    The frontend groups stations into boroughs and computes borough totals.
    Returned alongside lat/lon so the frontend can do point-in-polygon assignment.
    """
    sql = f"""
        SELECT
            station_id,
            station_name,
            lat,
            lon,
            ROUND(AVG(stockout_minutes), 1)         AS avg_stockout_minutes,
            ROUND(AVG(full_minutes), 1)              AS avg_full_minutes,
            ROUND(AVG(avg_availability_ratio), 3)   AS avg_availability_ratio,
            COUNT(DISTINCT service_date)             AS days_with_data
        FROM `{_PROJECT}.marts_cdmx.mart_ecobici_stockout_daily`
        WHERE service_date >= DATE_SUB(CURRENT_DATE('America/Mexico_City'), INTERVAL {days} DAY)
        GROUP BY station_id, station_name, lat, lon
        ORDER BY avg_stockout_minutes DESC
    """
    return _q(sql)
