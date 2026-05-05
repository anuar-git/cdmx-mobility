"""hourly_realtime_pipeline — light hourly refresh for EcoBici Gold data.

Triggers an explicit EcoBici Cloud Run ingest (one snapshot), waits for it to
land in GCS, runs the Dataproc ecobici Silver job for today's date, then
refreshes the fct_ecobici_station_hourly dbt model.

Note on Dataproc latency: cluster startup takes ~3 min. With the :05 schedule
this means Gold is refreshed ~8-10 min after each hour. That is acceptable for
near-real-time Tableau views. For sub-minute latency a streaming job (Beam +
Dataflow) would be needed — out of scope for Phase 4.

The daily_mobility_pipeline also processes EcoBici as part of the full daily
batch. The two DAGs are independent — the hourly pipeline writes to the same
Silver / Gold tables with mode="overwrite" on today's partition, so they are
idempotent.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml
from airflow.decorators import dag
from airflow.operators.bash import BashOperator
from airflow.providers.google.cloud.operators.cloud_run import CloudRunExecuteJobOperator
from airflow.providers.google.cloud.operators.dataproc import (
    DataprocInstantiateWorkflowTemplateOperator,
)
from airflow.providers.google.cloud.sensors.gcs import GCSObjectsWithPrefixExistenceSensor

_CFG_PATH = Path(__file__).parent.parent / "config" / "hourly_pipeline.yml"
_CFG = yaml.safe_load(_CFG_PATH.read_text())

_PROJECT = _CFG["gcp_project"]
_REGION = _CFG["region"]
_BUCKET = _CFG["gcs_data_bucket"]


@dag(
    dag_id=_CFG["dag_id"],
    schedule=_CFG["schedule"],
    start_date=datetime.datetime.fromisoformat(_CFG["start_date"]),
    catchup=False,
    max_active_runs=_CFG["max_active_runs"],
    default_args={
        "retries": _CFG["default_args"]["retries"],
        "retry_delay": datetime.timedelta(minutes=_CFG["default_args"]["retry_delay_minutes"]),
    },
    tags=["hourly", "ecobici"],
    doc_md=__doc__,
)
def hourly_realtime_pipeline() -> None:
    trigger = CloudRunExecuteJobOperator(
        task_id="trigger_ecobici",
        project_id=_PROJECT,
        region=_REGION,
        job_name=_CFG["cloud_run_job"],
    )

    # Wait for any snapshot whose prefix matches the current hour, e.g.
    # ecobici/station_status/ingestion_ts=2026-04-27T14 matches
    # ecobici/station_status/ingestion_ts=2026-04-27T14-05/station_status.json
    wait = GCSObjectsWithPrefixExistenceSensor(
        task_id="wait_for_snapshot",
        bucket=_BUCKET,
        prefix="ecobici/station_status/ingestion_ts={{ execution_date.strftime('%Y-%m-%dT%H') }}",
        google_cloud_conn_id="google_cloud_default",
        poke_interval=_CFG["ecobici_sensor_poke_interval_seconds"],
        timeout=_CFG["ecobici_sensor_timeout_seconds"],
        mode="reschedule",
    )

    spark = DataprocInstantiateWorkflowTemplateOperator(
        task_id="spark_ecobici_silver",
        project_id=_PROJECT,
        region=_REGION,
        template_id=_CFG["dataproc_template"],
        parameters={"INPUT_DATE": "{{ ds }}"},
    )

    dbt_refresh = BashOperator(
        task_id="dbt_refresh_ecobici",
        bash_command=(
            "cd /opt/dbt_bigquery && "
            "dbt run --select {{ params.selector }} "
            "--profiles-dir /opt/dbt_bigquery --target prod"
        ),
        params={"selector": _CFG["dbt_selector"]},
        env={"GCP_PROJECT_ID": _PROJECT},
        append_env=True,
    )

    trigger >> wait >> spark >> dbt_refresh


hourly_realtime_pipeline()
