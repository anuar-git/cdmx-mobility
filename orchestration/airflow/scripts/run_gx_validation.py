"""Run Great Expectations validations against Silver tables and write results to BQ.

Uses the GE 1.x ephemeral context + pandas datasource to avoid SQLAlchemy/
BigQuery connector dependencies. Each validation pulls a day-partition sample
via BQ Storage API into a pandas DataFrame, validates it, then writes a summary
row to meta_cdmx.gx_validation_results.

Expectations per table:
  ecobici_state_changes  -- station_id not null, bikes/docks 0-200
  metro_affluence        -- station_canonical not null, daily_entries >= 0
  metrobus_stop_events   -- vehicle_id not null, dwell_seconds >= 0
  weather_hourly_fact    -- obs_timestamp not null, temperature -10-50, humidity 0-100
"""

from __future__ import annotations

import datetime
from collections.abc import Callable

# Expectations: list of (callable that takes validator, runs expectations)
_SUITE_EXPECTATIONS: dict[str, Callable] = {}


def _suite(name: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        _SUITE_EXPECTATIONS[name] = fn
        return fn

    return decorator


@_suite("silver_ecobici_state_changes")
def _ecobici_expectations(validator: object) -> None:
    validator.expect_column_values_to_not_be_null("station_id")
    validator.expect_column_values_to_not_be_null("snapshot_ts")
    validator.expect_column_values_to_be_between("num_bikes_available", min_value=0, max_value=200)
    validator.expect_column_values_to_be_between("num_docks_available", min_value=0, max_value=200)


@_suite("silver_metro_affluence")
def _metro_expectations(validator: object) -> None:
    validator.expect_column_values_to_not_be_null("station_canonical")
    validator.expect_column_values_to_not_be_null("linea")
    validator.expect_column_values_to_be_between("daily_entries", min_value=0)


@_suite("silver_metrobus_stop_events")
def _metrobus_expectations(validator: object) -> None:
    validator.expect_column_values_to_not_be_null("vehicle_id")
    validator.expect_column_values_to_not_be_null("stop_id")
    validator.expect_column_values_to_be_between("dwell_seconds", min_value=0)


@_suite("silver_weather_hourly_fact")
def _weather_expectations(validator: object) -> None:
    validator.expect_column_values_to_not_be_null("obs_timestamp")
    validator.expect_column_values_to_be_between("avg_temperature_2m", min_value=-10, max_value=50)
    validator.expect_column_values_to_be_between(
        "avg_relativehumidity_2m", min_value=0, max_value=100
    )
    validator.expect_column_values_to_be_between("avg_windspeed_10m", min_value=0)


# BQ table name for each suite (within silver_cdmx dataset)
_SUITE_TABLE: dict[str, str] = {
    "silver_ecobici_state_changes": "ecobici_state_changes",
    "silver_metro_affluence": "metro_affluence",
    "silver_metrobus_stop_events": "metrobus_stop_events",
    "silver_weather_hourly_fact": "weather_hourly_fact",
}


def _fetch_sample(
    project_id: str, table: str, run_date: str, sample_rows: int = 10_000
) -> pandas.DataFrame:  # noqa: F821
    from google.cloud import bigquery

    bq = bigquery.Client(project=project_id)
    query = f"""
        SELECT * EXCEPT(service_date)
        FROM `{project_id}.silver_cdmx.{table}`
        WHERE service_date = DATE('{run_date}')
        LIMIT {sample_rows}
    """
    return bq.query(query).to_dataframe()


def _run_single_validation(
    project_id: str,
    suite_name: str,
    table_name: str,
    run_date: str,
) -> dict:
    import great_expectations as gx

    df = _fetch_sample(project_id, table_name, run_date)
    recorded_at = datetime.datetime.utcnow().isoformat() + "Z"

    if df.empty:
        return {
            "run_date": run_date,
            "suite_name": suite_name,
            "table_name": table_name,
            "success": True,
            "evaluated_count": 0,
            "successful_count": 0,
            "unsuccessful_count": 0,
            "recorded_at": recorded_at,
        }

    context = gx.get_context(mode="ephemeral")
    datasource = context.sources.add_pandas(f"pandas_{suite_name}")
    asset = datasource.add_dataframe_asset(suite_name)
    batch_request = asset.build_batch_request(dataframe=df)

    context.add_or_update_expectation_suite(suite_name)
    validator = context.get_validator(
        batch_request=batch_request,
        expectation_suite_name=suite_name,
    )

    # Apply the expectations registered for this suite
    _SUITE_EXPECTATIONS[suite_name](validator)

    result = validator.validate()
    stats = result.statistics

    return {
        "run_date": run_date,
        "suite_name": suite_name,
        "table_name": table_name,
        "success": bool(result.success),
        "evaluated_count": stats.get("evaluated_expectations", 0),
        "successful_count": stats.get("successful_expectations", 0),
        "unsuccessful_count": stats.get("unsuccessful_expectations", 0),
        "recorded_at": recorded_at,
    }


def run_gx_validations(project_id: str, run_date: str, **_: object) -> None:
    """Validate all Silver tables and write one summary row per suite to BQ."""
    from google.cloud import bigquery

    bq = bigquery.Client(project=project_id)
    rows = []
    failures: list[str] = []

    for suite_name, table_name in _SUITE_TABLE.items():
        try:
            row = _run_single_validation(project_id, suite_name, table_name, run_date)
            rows.append(row)
            if not row["success"]:
                failed = row["unsuccessful_count"]
                total = row["evaluated_count"]
                failures.append(f"{suite_name}: {failed}/{total} expectations failed")
        except Exception as exc:
            failures.append(f"{suite_name}: validation error — {exc}")

    if rows:
        errors = bq.insert_rows_json(f"{project_id}.meta_cdmx.gx_validation_results", rows)
        if errors:
            raise RuntimeError(f"BQ insert errors (gx_validation_results): {errors}")

    if failures:
        raise RuntimeError("Great Expectations validation failures:\n" + "\n".join(failures))
