"""daily_mobility_pipeline — end-to-end daily batch pipeline.

Stages:
  1. ingest  — trigger Cloud Run ingestor jobs (weather, EcoBici, Metrobús email).
               Metro affluence ingest is handled by CI cron; a landing sensor
               waits for its GCS object regardless of how it arrived.
  2. sensors — GCSObjectExistenceSensor on each Bronze prefix for {{ ds }}.
               mode="reschedule" releases the worker slot between pokes.
  3. spark   — DataprocInstantiateWorkflowTemplateOperator, two parallel pairs
               to respect the 10-vCPU CPUS_ALL_REGIONS quota (8 vCPUs/cluster).
               Pair 1: weather + metro. Pair 2: ecobici + metrobus.
  4. dbt     — dbt build (create/replace tables) then dbt test.
  5. notify  — Slack success message.

Backfill any missed day:
    make backfill DATE=2026-03-15
or:
    airflow dags trigger daily_mobility_pipeline \\
      --run-id backfill_2026-03-15 --logical-date 2026-03-15T08:00:00Z
"""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml
from airflow.decorators import dag, task, task_group
from airflow.operators.bash import BashOperator
from airflow.providers.google.cloud.operators.cloud_run import CloudRunExecuteJobOperator
from airflow.providers.google.cloud.operators.dataproc import (
    DataprocInstantiateWorkflowTemplateOperator,
)
from airflow.providers.google.cloud.sensors.gcs import GCSObjectExistenceSensor
from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator

_CFG_PATH = Path(__file__).parent.parent / "config" / "daily_pipeline.yml"
_CFG = yaml.safe_load(_CFG_PATH.read_text())

_PROJECT = _CFG["gcp_project"]
_REGION = _CFG["region"]
_DATA_BUCKET = _CFG["gcs_data_bucket"]
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


def _on_sla_miss(dag, task_list, blocking_task_list, slas, blocking_tis):
    SlackWebhookOperator(
        task_id="_sla_miss",
        slack_webhook_conn_id="slack_cdmx",
        message=(
            f":warning: SLA miss on *{dag.dag_id}* — "
            f"tasks still running: {[t.task_id for t in task_list]}"
        ),
    ).execute({})


@dag(
    dag_id=_CFG["dag_id"],
    schedule=_CFG["schedule"],
    start_date=datetime.datetime.fromisoformat(_CFG["start_date"]),
    catchup=_CFG["catchup"],
    max_active_runs=_CFG["max_active_runs"],
    default_args={**_DEFAULT_ARGS, "on_failure_callback": _on_failure},
    tags=["daily", "production"],
    sla_miss_callback=_on_sla_miss,
    doc_md=__doc__,
)
def daily_mobility_pipeline() -> None:

    # ── 1. INGESTION ──────────────────────────────────────────────────────────
    @task_group(group_id="ingest")
    def ingest_group() -> None:
        CloudRunExecuteJobOperator(
            task_id="trigger_weather",
            project_id=_PROJECT,
            region=_REGION,
            job_name=_CFG["cloud_run_jobs"]["weather_ingest"],
            sla=_SLA,
        )
        CloudRunExecuteJobOperator(
            task_id="trigger_ecobici",
            project_id=_PROJECT,
            region=_REGION,
            job_name=_CFG["cloud_run_jobs"]["ecobici_ingest"],
            sla=_SLA,
        )
        CloudRunExecuteJobOperator(
            task_id="trigger_metrobus_email",
            project_id=_PROJECT,
            region=_REGION,
            job_name=_CFG["cloud_run_jobs"]["metrobus_email"],
            sla=_SLA,
        )
        # Metro affluence is a CKAN pull that runs via CI cron; we don't re-trigger
        # it from Airflow. The landing sensor below waits for its GCS object.

    # ── 2. LANDING SENSORS ────────────────────────────────────────────────────
    @task_group(group_id="wait_for_landing")
    def sensors_group() -> None:
        GCSObjectExistenceSensor(
            task_id="wait_weather",
            bucket=_DATA_BUCKET,
            # GCS prefix — sensor returns True when *any* object with this prefix exists.
            object=_CFG["landing_sensors"]["weather_prefix"],
            google_cloud_conn_id="google_cloud_default",
            poke_interval=300,
            timeout=3600,
            mode="reschedule",
            sla=_SLA,
        )
        GCSObjectExistenceSensor(
            task_id="wait_ecobici",
            bucket=_DATA_BUCKET,
            object=_CFG["landing_sensors"]["ecobici_prefix"],
            google_cloud_conn_id="google_cloud_default",
            poke_interval=60,
            timeout=1800,
            mode="reschedule",
            sla=_SLA,
        )
        GCSObjectExistenceSensor(
            task_id="wait_metrobus",
            bucket=_DATA_BUCKET,
            object=_CFG["landing_sensors"]["metrobus_prefix"],
            google_cloud_conn_id="google_cloud_default",
            poke_interval=300,
            timeout=3600,
            mode="reschedule",
            sla=_SLA,
        )
        GCSObjectExistenceSensor(
            task_id="wait_metro",
            bucket=_RAW_BUCKET,
            object=_CFG["landing_sensors"]["metro_prefix"],
            google_cloud_conn_id="google_cloud_default",
            poke_interval=300,
            timeout=3600,
            mode="reschedule",
            sla=_SLA,
        )

    # ── 3. SPARK BRONZE → SILVER ──────────────────────────────────────────────
    # Two parallel pairs to respect the 10-vCPU CPUS_ALL_REGIONS quota.
    # Pair 1 (weather + metro) completes before pair 2 (ecobici + metrobus) starts.
    @task_group(group_id="spark_silver")
    def spark_group() -> None:
        spark_weather = DataprocInstantiateWorkflowTemplateOperator(
            task_id="spark_weather",
            project_id=_PROJECT,
            region=_REGION,
            template_id=_CFG["dataproc_templates"]["weather"],
            parameters={"INPUT_DATE": "{{ ds }}"},
            sla=_SLA,
        )
        spark_metro = DataprocInstantiateWorkflowTemplateOperator(
            task_id="spark_metro",
            project_id=_PROJECT,
            region=_REGION,
            template_id=_CFG["dataproc_templates"]["metro"],
            parameters={"INPUT_DATE": "{{ ds }}"},
            sla=_SLA,
        )
        spark_ecobici = DataprocInstantiateWorkflowTemplateOperator(
            task_id="spark_ecobici",
            project_id=_PROJECT,
            region=_REGION,
            template_id=_CFG["dataproc_templates"]["ecobici"],
            parameters={"INPUT_DATE": "{{ ds }}"},
            sla=_SLA,
        )
        spark_metrobus = DataprocInstantiateWorkflowTemplateOperator(
            task_id="spark_metrobus",
            project_id=_PROJECT,
            region=_REGION,
            template_id=_CFG["dataproc_templates"]["metrobus"],
            parameters={"INPUT_DATE": "{{ ds }}"},
            sla=_SLA,
        )

        # Sequential pairs — pair 1 frees its 8 vCPUs before pair 2 acquires them.
        _ = [spark_weather, spark_metro] >> [spark_ecobici, spark_metrobus]

    # ── 4. DBT BUILD + TEST ───────────────────────────────────────────────────
    # dbt-bigquery is installed in the Airflow image. The VM's SA has BigQuery
    # dataEditor + jobUser so no explicit credentials file is needed.
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            "cd /opt/dbt_bigquery && "
            "dbt build "
            "--select {{ params.selector }} "
            '--vars \'{"run_date": "{{ ds }}"}\' '
            "--profiles-dir /opt/dbt_bigquery --target prod"
        ),
        params={"selector": _CFG["dbt_daily_selector"].strip()},
        env={"GCP_PROJECT_ID": _PROJECT},
        sla=_SLA,
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            "cd /opt/dbt_bigquery && "
            "dbt test "
            "--select {{ params.selector }} "
            "--profiles-dir /opt/dbt_bigquery --target prod"
        ),
        params={"selector": _CFG["dbt_daily_selector"].strip()},
        env={"GCP_PROJECT_ID": _PROJECT},
        sla=_SLA,
    )

    # ── 5. SUCCESS NOTIFICATION ───────────────────────────────────────────────
    @task
    def notify_success(**context: dict) -> None:
        ds = context["ds"]
        SlackWebhookOperator(
            task_id="_slack_ok",
            slack_webhook_conn_id="slack_cdmx",
            message=(
                f":large_green_circle: *daily_mobility_pipeline* complete for `{ds}`.\n"
                f"Silver + Gold refreshed. All dbt tests passed."
            ),
        ).execute(context)

    # ── DAG WIRING ────────────────────────────────────────────────────────────
    ingest = ingest_group()
    sensors = sensors_group()
    spark = spark_group()
    success = notify_success()

    ingest >> sensors >> spark >> dbt_build >> dbt_test >> success


daily_mobility_pipeline()
