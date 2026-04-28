"""Check Silver-layer freshness against per-source SLA thresholds.

Queries the max timestamp in each Silver table, computes lag vs. now(),
writes one row per source to meta_cdmx.freshness_sla_log, then raises
AirflowException if any SLA is violated so the on_failure_callback fires
the Slack alert.

SLA targets (all measured from current UTC wall-clock time):
  ecobici  — 10 min  (Cloud Run job every 10 min + Spark within 30 min of DAG start)
  weather  — 120 min (daily ingest + Spark run)
  metro    — 1440 min (once-daily CKAN pull)
  metrobus — 60 min  (sinopticoplus email ingest every 5 min + Spark)
"""

from __future__ import annotations

import datetime

# (canonical_source, bq_table, timestamp_column, sla_minutes)
_CHECKS: list[tuple[str, str, str, int]] = [
    ("ecobici", "ecobici_state_changes", "snapshot_ts", 10),
    ("weather", "weather_hourly_fact", "obs_timestamp", 120),
    ("metro", "metro_affluence", "service_date", 1440),
    ("metrobus", "metrobus_stop_events", "dwell_start_ts", 60),
]


def check_freshness_slas(project_id: str, **_: object) -> None:
    from google.cloud import bigquery

    bq = bigquery.Client(project=project_id)
    now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.UTC)
    checked_at = now_utc.isoformat()

    rows: list[dict] = []
    violated: list[str] = []

    for source, table, ts_col, sla_minutes in _CHECKS:
        query = f"""
            SELECT MAX({ts_col}) AS latest_ts
            FROM `{project_id}.silver_cdmx.{table}`
        """
        result = list(bq.query(query).result())
        latest_ts = result[0]["latest_ts"] if result else None

        if latest_ts is None:
            lag_minutes = None
            is_violated = True
        else:
            # BQ returns DATE as datetime.date for service_date column
            if isinstance(latest_ts, datetime.date) and not isinstance(
                latest_ts, datetime.datetime
            ):
                latest_ts = datetime.datetime(
                    latest_ts.year, latest_ts.month, latest_ts.day, tzinfo=datetime.UTC
                )
            elif latest_ts.tzinfo is None:
                latest_ts = latest_ts.replace(tzinfo=datetime.UTC)

            lag_minutes = round((now_utc - latest_ts).total_seconds() / 60, 2)
            is_violated = lag_minutes > sla_minutes

        rows.append(
            {
                "source": source,
                "latest_ts": latest_ts.isoformat() if latest_ts else None,
                "sla_minutes": sla_minutes,
                "lag_minutes": lag_minutes,
                "is_violated": is_violated,
                "checked_at": checked_at,
            }
        )

        if is_violated:
            lag_str = f"{lag_minutes:.0f} min stale" if lag_minutes is not None else "no data"
            violated.append(f"{source}: {lag_str} (SLA: {sla_minutes} min)")

    errors = bq.insert_rows_json(f"{project_id}.meta_cdmx.freshness_sla_log", rows)
    if errors:
        raise RuntimeError(f"BQ insert errors (freshness_sla_log): {errors}")

    if violated:
        raise RuntimeError(
            "Freshness SLA violated for:\n" + "\n".join(f"  • {v}" for v in violated)
        )
