"""Parse dbt run_results.json + manifest.json and stream rows to BigQuery.

Called as an Airflow @task after dbt_build completes. Reads the dbt target/
directory from the Airflow VM's working dbt project path, splits results into
model rows (dbt_run_results) and test rows (dbt_test_results), and inserts
both via the BQ streaming API.
"""

from __future__ import annotations

import datetime
import json
import pathlib

_DBT_TARGET = pathlib.Path("/opt/dbt_bigquery/target")


def upload_dbt_artifacts(project_id: str, run_date: str, **_: object) -> None:
    from google.cloud import bigquery

    run_results_path = _DBT_TARGET / "run_results.json"
    manifest_path = _DBT_TARGET / "manifest.json"

    if not run_results_path.exists():
        raise FileNotFoundError(f"dbt run_results.json not found at {run_results_path}")

    run_results = json.loads(run_results_path.read_text())
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"nodes": {}}

    recorded_at = datetime.datetime.utcnow().isoformat() + "Z"
    model_rows: list[dict] = []
    test_rows: list[dict] = []

    for result in run_results.get("results", []):
        unique_id = result["unique_id"]
        node_type = unique_id.split(".")[0]  # model / test / seed / snapshot
        node = manifest["nodes"].get(unique_id, {})

        base = {
            "run_date": run_date,
            "unique_id": unique_id,
            "node_name": node.get("name") or unique_id.split(".")[-1],
            "status": result["status"],
            "recorded_at": recorded_at,
        }

        if node_type in ("model", "seed", "snapshot"):
            adapter_response = result.get("adapter_response") or {}
            model_rows.append(
                {
                    **base,
                    "node_schema": node.get("schema"),
                    "execution_ms": round((result.get("execution_time") or 0) * 1000, 2),
                    "rows_affected": adapter_response.get("rows_affected"),
                }
            )
        elif node_type == "test":
            test_rows.append(
                {
                    **base,
                    "failures": result.get("failures") or 0,
                }
            )

    bq = bigquery.Client(project=project_id)

    if model_rows:
        errors = bq.insert_rows_json(f"{project_id}.meta_cdmx.dbt_run_results", model_rows)
        if errors:
            raise RuntimeError(f"BQ insert errors (dbt_run_results): {errors}")

    if test_rows:
        errors = bq.insert_rows_json(f"{project_id}.meta_cdmx.dbt_test_results", test_rows)
        if errors:
            raise RuntimeError(f"BQ insert errors (dbt_test_results): {errors}")
