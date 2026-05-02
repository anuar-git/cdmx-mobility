"""monthly_metro_pipeline — processes new CKAN metro affluence data to Silver.

The metro affluence dataset (datos.cdmx.gob.mx) is a cumulative historical CSV
updated roughly once per month. CI cron polls CKAN daily (06:00 CDMX) and uploads
the new dump when it appears, writing to:
  gs://cdmx-mobility-raw/metro/affluence_simple/ingestion_date=<ci-run-date>/

This DAG fires on the 1st of each month, waits (up to 25 days) for a new Bronze
partition to land in that calendar month, then runs the Spark Bronze→Silver job
to refresh the full metro Silver dataset (2010-present).

Spark is passed INPUT_DATE="" to scan all Bronze partitions — each CKAN dump is
a full historical replacement, not an incremental append.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml
from airflow.decorators import dag
from airflow.providers.google.cloud.operators.dataproc import (
    DataprocInstantiateWorkflowTemplateOperator,
)
from airflow.providers.google.cloud.sensors.gcs import GCSObjectsWithPrefixExistenceSensor
from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator

_CFG_PATH = Path(__file__).parent.parent / "config" / "monthly_metro_pipeline.yml"
_CFG = yaml.safe_load(_CFG_PATH.read_text())

_PROJECT = _CFG["gcp_project"]
_REGION = _CFG["region"]
_RAW_BUCKET = _CFG["gcs_raw_bucket"]
_SLA = datetime.timedelta(seconds=_CFG["sla_miss_seconds"])

_DEFAULT_ARGS: dict = {
    "retries": _CFG["default_args"]["retries"],
    "retry_delay": datetime.timedelta(minutes=_CFG["default_args"]["retry_delay_minutes"]),
    "retry_exponential_backoff": _CFG["default_args"]["retry_exponential_backoff"],
    "email_on_failure": _CFG["default_args"]["email_on_failure"],
    "email": [_CFG["default_args"]["email"]],
}


def _on_failure(context: dict) -> None:
    dag_id = context["dag"].dag_id
    task_id = context["task_instance"].task_id
    ds = context["ds"]
    log_url = context["task_instance"].log_url
    SlackWebhookOperator(
        task_id="_slack_failure",
        slack_webhook_conn_id="slack_cdmx",
        message=(f":red_circle: *{dag_id}* > `{task_id}` failed for `{ds}`\n<{log_url}|View logs>"),
    ).execute(context)


@dag(
    dag_id=_CFG["dag_id"],
    schedule=_CFG["schedule"],
    start_date=datetime.datetime.fromisoformat(_CFG["start_date"]),
    catchup=_CFG["catchup"],
    max_active_runs=_CFG["max_active_runs"],
    default_args={**_DEFAULT_ARGS, "on_failure_callback": _on_failure},
    tags=["monthly", "metro", "production"],
    doc_md=__doc__,
)
def monthly_metro_pipeline() -> None:

    wait_metro = GCSObjectsWithPrefixExistenceSensor(
        task_id="wait_metro",
        bucket=_RAW_BUCKET,
        prefix=_CFG["metro_bronze_prefix"],
        google_cloud_conn_id="google_cloud_default",
        poke_interval=3600,
        timeout=25 * 24 * 3600,  # wait up to 25 days for CKAN to release
        mode="reschedule",
        sla=_SLA,
    )

    spark_metro = DataprocInstantiateWorkflowTemplateOperator(
        task_id="spark_metro",
        project_id=_PROJECT,
        region=_REGION,
        template_id=_CFG["dataproc_template"],
        parameters={"INPUT_DATE": ""},
        sla=_SLA,
    )

    wait_metro >> spark_metro


monthly_metro_pipeline()
