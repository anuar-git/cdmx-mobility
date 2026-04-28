"""weekly_backfill_check — data quality report across the last 7 days of Gold data.

Runs Great Expectations checks against marts_cdmx BigQuery tables and posts a
quality summary to Slack. Expectations are declared in config/weekly_check.yml
so they can be adjusted without touching Python.

Failures do not block the pipeline — this DAG is purely observational.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import yaml
from airflow.decorators import dag, task
from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator

_CFG_PATH = Path(__file__).parent.parent / "config" / "weekly_check.yml"
_CFG = yaml.safe_load(_CFG_PATH.read_text())

_PROJECT = _CFG["gcp_project"]
_LOOKBACK = _CFG["lookback_days"]


@dag(
    dag_id=_CFG["dag_id"],
    schedule=_CFG["schedule"],
    start_date=datetime.datetime.fromisoformat(_CFG["start_date"]),
    catchup=False,
    default_args={
        "retries": _CFG["default_args"]["retries"],
        "retry_delay": datetime.timedelta(minutes=_CFG["default_args"]["retry_delay_minutes"]),
    },
    tags=["quality", "weekly"],
    doc_md=__doc__,
)
def weekly_backfill_check() -> None:

    @task
    def run_gx_checks(**context: Any) -> dict:
        """Query each Gold model and run the declared GX expectations."""
        import great_expectations as gx
        from google.cloud import bigquery

        bq = bigquery.Client(project=_PROJECT)
        ds = context["ds"]
        results: dict[str, dict] = {}

        for check_spec in _CFG["checks"]:
            model = check_spec["model"]
            dataset = check_spec["dataset"]
            table = f"{_PROJECT}.{dataset}.{model}"

            # Limit the query to the lookback window for efficiency.
            query = (
                f"SELECT * FROM `{table}` "
                f"WHERE service_date >= DATE_SUB('{ds}', INTERVAL {_LOOKBACK} DAY) "
                f"  AND service_date <= '{ds}'"
            )
            df = bq.query(query).to_dataframe()

            ctx = gx.get_context(mode="ephemeral")
            source = ctx.sources.add_pandas(name=model)
            asset = source.add_dataframe_asset(name=model)
            batch_req = asset.build_batch_request(dataframe=df)

            suite = ctx.add_expectation_suite(expectation_suite_name=model)
            for exp in check_spec["expectations"]:
                exp_type = exp["type"]
                exp_kwargs = exp.get("kwargs", {})
                getattr(suite, f"add_{exp_type}")(**exp_kwargs)

            validator = ctx.get_validator(batch_request=batch_req, expectation_suite=suite)
            result = validator.validate()

            results[model] = {
                "passed": result.statistics["successful_expectations"],
                "failed": result.statistics["unsuccessful_expectations"],
                "success": result.success,
                "rows_checked": len(df),
            }

        return results

    @task
    def post_report(results: dict, **context: Any) -> None:
        ds = context["ds"]
        lines = [f":bar_chart: *Weekly Data Quality Report* — week ending `{ds}`\n"]
        all_ok = True

        for model, r in results.items():
            icon = ":white_check_mark:" if r["success"] else ":x:"
            lines.append(
                f"{icon} `{model}` — "
                f"{r['passed']} passed / {r['failed']} failed "
                f"({r['rows_checked']:,} rows checked)"
            )
            if not r["success"]:
                all_ok = False

        if all_ok:
            lines.append("\n:tada: All checks passed!")
        else:
            lines.append("\n:fire: Failures detected — investigate marts_cdmx")

        SlackWebhookOperator(
            task_id="_post_slack",
            slack_webhook_conn_id="slack_cdmx",
            message="\n".join(lines),
        ).execute(context)

    results = run_gx_checks()
    post_report(results)


weekly_backfill_check()
