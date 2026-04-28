"""Pipeline health endpoints backed by meta_cdmx and marts_cdmx BigQuery tables."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Query
from google.cloud import bigquery

router = APIRouter(prefix="/api/pipeline")

_PROJECT = os.getenv("CDMX_GCP_PROJECT_ID", "cdmx-mobility-prod")


@lru_cache(maxsize=1)
def _bq_client() -> bigquery.Client:
    return bigquery.Client(project=_PROJECT)


def _query(sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in _bq_client().query(sql).result()]


@router.get("/health")
def pipeline_health(days: int = Query(default=30, ge=1, le=365)) -> list[dict]:
    """Dim pipeline health — one row per (run_date, canonical_source)."""
    sql = f"""
        SELECT
            CAST(run_date AS STRING)            AS run_date,
            canonical_source,
            total_rows_ingested,
            ingest_success_runs,
            ingest_error_runs,
            ingest_skipped_runs,
            dbt_total_runtime_seconds,
            dbt_test_pass_rate_pct,
            gx_pass_rate_pct,
            gx_all_suites_passed,
            freshness_lag_minutes,
            freshness_sla_minutes,
            freshness_sla_violated,
        FROM `{_PROJECT}.marts_cdmx.dim_pipeline_health`
        WHERE run_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
        ORDER BY run_date DESC, canonical_source
    """
    return _query(sql)


@router.get("/freshness")
def pipeline_freshness() -> list[dict]:
    """Latest freshness SLA status per source (most recent check only)."""
    sql = f"""
        SELECT
            source,
            CAST(latest_ts AS STRING)           AS latest_ts,
            lag_minutes,
            sla_minutes,
            is_violated,
            CAST(checked_at AS STRING)          AS checked_at,
        FROM `{_PROJECT}.meta_cdmx.freshness_sla_log`
        WHERE DATE(checked_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 DAY)
        QUALIFY ROW_NUMBER() OVER (PARTITION BY source ORDER BY checked_at DESC) = 1
        ORDER BY source
    """
    return _query(sql)


@router.get("/tests")
def pipeline_tests(days: int = Query(default=30, ge=1, le=365)) -> list[dict]:
    """dbt test pass rate per run_date (pipeline-wide, not per source)."""
    sql = f"""
        SELECT
            CAST(run_date AS STRING)            AS run_date,
            dbt_tests_passed,
            dbt_tests_failed,
            dbt_tests_total,
            dbt_test_pass_rate_pct,
        FROM (
            SELECT
                run_date,
                MAX(dbt_tests_passed)           AS dbt_tests_passed,
                MAX(dbt_tests_failed)           AS dbt_tests_failed,
                MAX(dbt_tests_total)            AS dbt_tests_total,
                MAX(dbt_test_pass_rate_pct)     AS dbt_test_pass_rate_pct,
            FROM `{_PROJECT}.marts_cdmx.dim_pipeline_health`
            WHERE run_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
            GROUP BY run_date
        )
        ORDER BY run_date DESC
    """
    return _query(sql)


@router.get("/runtime")
def pipeline_runtime(days: int = Query(default=30, ge=1, le=365)) -> list[dict]:
    """dbt total runtime in seconds per run_date."""
    sql = f"""
        SELECT
            CAST(run_date AS STRING)            AS run_date,
            MAX(dbt_total_runtime_seconds)      AS dbt_total_runtime_seconds,
            MAX(dbt_models_succeeded)           AS dbt_models_succeeded,
            MAX(dbt_models_failed)              AS dbt_models_failed,
        FROM `{_PROJECT}.marts_cdmx.dim_pipeline_health`
        WHERE run_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
        GROUP BY run_date
        ORDER BY run_date DESC
    """
    return _query(sql)


@router.get("/ingestion")
def pipeline_ingestion(days: int = Query(default=30, ge=1, le=365)) -> list[dict]:
    """Ingestion row counts per (run_date, canonical_source)."""
    sql = f"""
        SELECT
            CAST(run_date AS STRING)            AS run_date,
            canonical_source,
            total_rows_ingested,
            total_bytes,
            total_files,
            ingest_success_runs,
            ingest_error_runs,
        FROM `{_PROJECT}.marts_cdmx.dim_pipeline_health`
        WHERE run_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
        ORDER BY run_date DESC, canonical_source
    """
    return _query(sql)
