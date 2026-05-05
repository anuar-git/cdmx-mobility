"""daily_mobility_pipeline — end-to-end daily batch pipeline.

Stages:
  1. ingest  — trigger Cloud Run ingestor jobs (weather, EcoBici, Metrobús email).
  2. sensors — GCSObjectExistenceSensor on each Bronze prefix for {{ ds }}.
               mode="reschedule" releases the worker slot between pokes.
  3. spark   — DataprocInstantiateWorkflowTemplateOperator, one anchor (weather)
               then two parallel jobs (ecobici + metrobus), to respect the
               10-vCPU CPUS_ALL_REGIONS quota (8 vCPUs/cluster).
               Metro affluence Spark runs separately in monthly_metro_pipeline.
  4. gx      — Great Expectations validation on all four Silver tables.
               Writes one summary row per suite to meta_cdmx.gx_validation_results.
  5. dbt     — dbt build (create/replace tables) then dbt test.
  6. observe — Upload dbt run artifacts to BQ, then check Silver freshness SLAs.
  7. notify  — Slack success message.

Backfill any missed day:
    make backfill DATE=2026-03-15
or:
    airflow dags trigger daily_mobility_pipeline \\
      --run-id backfill_2026-03-15 --logical-date 2026-03-15T08:00:00Z
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import yaml
from airflow.decorators import dag, task, task_group
from airflow.operators.bash import BashOperator
from airflow.providers.google.cloud.operators.cloud_run import CloudRunExecuteJobOperator
from airflow.providers.google.cloud.operators.dataproc import (
    DataprocInstantiateWorkflowTemplateOperator,
)
from airflow.providers.google.cloud.sensors.gcs import GCSObjectsWithPrefixExistenceSensor
from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator

_CFG_PATH = Path(__file__).parent.parent / "config" / "daily_pipeline.yml"
_CFG = yaml.safe_load(_CFG_PATH.read_text())

_PROJECT = _CFG["gcp_project"]
_REGION = _CFG["region"]
_DATA_BUCKET = _CFG["gcs_data_bucket"]
_SLA = datetime.timedelta(seconds=_CFG["sla_miss_seconds"])

_DEFAULT_ARGS: dict = {
    "retries": _CFG["default_args"]["retries"],
    "retry_delay": datetime.timedelta(minutes=_CFG["default_args"]["retry_delay_minutes"]),
    "retry_exponential_backoff": _CFG["default_args"]["retry_exponential_backoff"],
    "email_on_failure": _CFG["default_args"]["email_on_failure"],
    "email": [_CFG["default_args"]["email"]],
}

# Add scripts directory to path so the Airflow worker can import the callables.
_SCRIPTS_DIR = str(Path(__file__).parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


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
        GCSObjectsWithPrefixExistenceSensor(
            task_id="wait_weather",
            bucket=_DATA_BUCKET,
            prefix=_CFG["landing_sensors"]["weather_prefix"],
            google_cloud_conn_id="google_cloud_default",
            poke_interval=300,
            timeout=3600,
            mode="reschedule",
            sla=_SLA,
        )
        GCSObjectsWithPrefixExistenceSensor(
            task_id="wait_ecobici",
            bucket=_DATA_BUCKET,
            prefix=_CFG["landing_sensors"]["ecobici_prefix"],
            google_cloud_conn_id="google_cloud_default",
            poke_interval=60,
            timeout=1800,
            mode="reschedule",
            sla=_SLA,
        )
        GCSObjectsWithPrefixExistenceSensor(
            task_id="wait_metrobus",
            bucket=_DATA_BUCKET,
            prefix=_CFG["landing_sensors"]["metrobus_prefix"],
            google_cloud_conn_id="google_cloud_default",
            poke_interval=300,
            timeout=3600,
            mode="reschedule",
            sla=_SLA,
        )

    # ── 3. SPARK BRONZE → SILVER ──────────────────────────────────────────────
    # Jobs run sequentially: weather → ecobici → metrobus.
    # Parallel execution was limited by IN_USE_ADDRESSES quota (8 external IPs):
    # Airflow VM (1) + two clusters (4+4) = 9, which exceeds the quota.
    # Sequential peak is 5 IPs (VM + one cluster). Adds ~15-30 min vs parallel.
    # Metro Silver runs separately in monthly_metro_pipeline.
    @task_group(group_id="spark_silver")
    def spark_group() -> None:
        spark_weather = DataprocInstantiateWorkflowTemplateOperator(
            task_id="spark_weather",
            project_id=_PROJECT,
            region=_REGION,
            template_id=_CFG["dataproc_templates"]["weather"],
            parameters={"INPUT_DATE": "{{ yesterday_ds }}"},
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

        spark_weather >> spark_ecobici >> spark_metrobus

    # ── 4. GREAT EXPECTATIONS — SILVER VALIDATION ────────────────────────────
    # Runs after Silver is written, before dbt consumes it. Validates a
    # same-day sample from each Silver table. Fails the DAG (and fires the
    # on_failure_callback → Slack) if any expectation fails.
    @task(task_id="gx_validate_silver", sla=_SLA)
    def gx_validate_silver(run_date: str, **context: dict) -> None:
        from run_gx_validation import run_gx_validations

        run_gx_validations(project_id=_PROJECT, run_date=run_date)

    # ── 5. DBT BUILD + TEST ───────────────────────────────────────────────────
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            "cd /opt/dbt_bigquery && "
            "dbt deps --profiles-dir /opt/dbt_bigquery --target prod && "
            "dbt build "
            "--select {{ params.selector }} "
            '--vars \'{"run_date": "{{ ds }}"}\' '
            "--profiles-dir /opt/dbt_bigquery --target prod"
        ),
        params={"selector": _CFG["dbt_daily_selector"].strip()},
        env={"GCP_PROJECT_ID": _PROJECT},
        append_env=True,
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
        append_env=True,
        sla=_SLA,
    )

    # ── 6. OBSERVABILITY ─────────────────────────────────────────────────────
    # upload_dbt_artifacts must run after dbt_build so target/run_results.json exists.
    # check_freshness runs after dbt_test (full pipeline complete) so lags are final.
    @task(task_id="upload_dbt_artifacts", sla=_SLA)
    def upload_dbt_artifacts_task(run_date: str, **_: dict) -> None:
        from upload_dbt_artifacts import upload_dbt_artifacts

        upload_dbt_artifacts(project_id=_PROJECT, run_date=run_date)

    @task(task_id="check_freshness_slas", sla=_SLA)
    def check_freshness_task(**_: dict) -> None:
        from check_freshness import check_freshness_slas

        check_freshness_slas(project_id=_PROJECT)

    # ── 7. SUCCESS NOTIFICATION ───────────────────────────────────────────────
    @task
    def notify_success(**context: dict) -> None:
        ds = context["ds"]
        SlackWebhookOperator(
            task_id="_slack_ok",
            slack_webhook_conn_id="slack_cdmx",
            message=(
                f":large_green_circle: *daily_mobility_pipeline* complete for `{ds}`.\n"
                f"Silver + Gold refreshed. All dbt tests passed. Freshness SLAs OK."
            ),
        ).execute(context)

    # ── DAG WIRING ────────────────────────────────────────────────────────────
    ingest = ingest_group()
    sensors = sensors_group()
    spark = spark_group()
    gx = gx_validate_silver(run_date="{{ ds }}")
    artifacts = upload_dbt_artifacts_task(run_date="{{ ds }}")
    freshness = check_freshness_task()
    success = notify_success()

    ingest >> sensors >> spark >> gx >> dbt_build >> artifacts >> dbt_test >> freshness >> success


daily_mobility_pipeline()
