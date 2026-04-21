"""Unit tests for bronze_to_silver_weather.py.

All tests use local Spark and write NDJSON fixtures to pytest's tmp_path.
Fixtures use all 5 real coordinate IDs (matching COORDINATE_IDS) so that
pivot column names and city-wide averages are correct.

Coverage:
  _load_hourly         -- array unzip + explode, correct row count
  _pivot_by_coordinate -- column naming, row count after pivot
  _city_wide_averages  -- correct arithmetic mean
  _add_derived_features -- each formula: heat_index range, comfort_score
                           clipping, precipitation_flag threshold, wind_category
  _transform           -- end-to-end schema correctness, service_date extraction
"""

import json
import os

from pyspark.sql import SparkSession

from spark_jobs.bronze_to_silver_weather import (
    COORDINATE_IDS,
    PRECIP_THRESHOLD_MM,
    TEMP_IDEAL_C,
    WIND_CALM_MS,
    WIND_STRONG_MS,
    WIND_WEIGHT,
    _add_derived_features,
    _city_wide_averages,
    _load_hourly,
    _pivot_by_coordinate,
    _transform,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_N_HOURS = 2
_TIMES = ["2026-04-19T00:00", "2026-04-19T01:00"]


def _make_line(
    coord_id: str, temperature: float, precipitation: float, windspeed: float, humidity: float
) -> str:
    """Build one NDJSON line for a coordinate with uniform hourly values."""
    return json.dumps(
        {
            "coordinate_id": coord_id,
            "latitude": 19.4326,
            "longitude": -99.1332,
            "fetch_date": "2026-04-19",
            "hourly": {
                "time": _TIMES,
                "temperature_2m": [temperature] * _N_HOURS,
                "precipitation": [precipitation] * _N_HOURS,
                "windspeed_10m": [windspeed] * _N_HOURS,
                "relativehumidity_2m": [humidity] * _N_HOURS,
            },
        }
    )


def _write_fixture(
    tmp_path,
    temperature: float = 20.0,
    precipitation: float = 0.0,
    windspeed: float = 2.0,
    humidity: float = 60.0,
) -> str:
    """Write a full 5-coordinate NDJSON fixture with uniform values; return path glob."""
    lines = [
        _make_line(cid, temperature, precipitation, windspeed, humidity) for cid in COORDINATE_IDS
    ]
    filepath = os.path.join(tmp_path, "weather_2026-04-19.json")
    with open(filepath, "w") as f:
        f.write("\n".join(lines))
    return str(tmp_path / "*.json")


def _features_for(spark: SparkSession, tmp_path, **fixture_kwargs):
    """Run the full pipeline up to derived features; return collected rows."""
    glob = _write_fixture(tmp_path, **fixture_kwargs)
    df = _add_derived_features(_city_wide_averages(_pivot_by_coordinate(_load_hourly(spark, glob))))
    return df.collect()


# ---------------------------------------------------------------------------
# _load_hourly tests
# ---------------------------------------------------------------------------


def test_load_hourly_row_count(spark: SparkSession, tmp_path):
    """5 coordinates x 2 hours = 10 rows after explode."""
    glob = _write_fixture(tmp_path)
    df = _load_hourly(spark, glob)
    assert df.count() == len(COORDINATE_IDS) * _N_HOURS


def test_load_hourly_schema(spark: SparkSession, tmp_path):
    """Output has coordinate_id, obs_time, and all four metric columns."""
    glob = _write_fixture(tmp_path)
    df = _load_hourly(spark, glob)
    expected = {
        "coordinate_id",
        "obs_time",
        "temperature_2m",
        "precipitation",
        "windspeed_10m",
        "relativehumidity_2m",
    }
    assert expected.issubset(set(df.columns))


def test_load_hourly_values(spark: SparkSession, tmp_path):
    """temperature_2m values match the fixture constant."""
    glob = _write_fixture(tmp_path, temperature=22.5)
    df = _load_hourly(spark, glob)
    temps = {r.temperature_2m for r in df.collect()}
    assert len(temps) == 1
    assert abs(next(iter(temps)) - 22.5) < 1e-4


# ---------------------------------------------------------------------------
# _pivot_by_coordinate tests
# ---------------------------------------------------------------------------


def test_pivot_row_count(spark: SparkSession, tmp_path):
    """After pivot: one row per hour (_N_HOURS rows)."""
    glob = _write_fixture(tmp_path)
    df = _pivot_by_coordinate(_load_hourly(spark, glob))
    assert df.count() == _N_HOURS


def test_pivot_column_names(spark: SparkSession, tmp_path):
    """Pivoted DataFrame has {coordinate_id}_{metric} columns for each coord."""
    glob = _write_fixture(tmp_path)
    df = _pivot_by_coordinate(_load_hourly(spark, glob))
    for cid in COORDINATE_IDS:
        assert f"{cid}_temperature_2m" in df.columns
        assert f"{cid}_precipitation" in df.columns


# ---------------------------------------------------------------------------
# _city_wide_averages tests
# ---------------------------------------------------------------------------


def test_city_avg_temperature_uniform(spark: SparkSession, tmp_path):
    """When all coordinates have the same temperature, avg equals that value."""
    temp = 18.0
    glob = _write_fixture(tmp_path, temperature=temp)
    df = _city_wide_averages(_pivot_by_coordinate(_load_hourly(spark, glob)))
    for row in df.collect():
        assert abs(row.avg_temperature_2m - temp) < 1e-3


def test_city_avg_columns_present(spark: SparkSession, tmp_path):
    """All four avg_* columns are added."""
    glob = _write_fixture(tmp_path)
    df = _city_wide_averages(_pivot_by_coordinate(_load_hourly(spark, glob)))
    for suffix in ("temperature_2m", "precipitation", "windspeed_10m", "relativehumidity_2m"):
        assert f"avg_{suffix}" in df.columns


# ---------------------------------------------------------------------------
# _add_derived_features tests
# ---------------------------------------------------------------------------


def test_precipitation_flag_false_below_threshold(spark: SparkSession, tmp_path):
    rows = _features_for(spark, tmp_path, precipitation=PRECIP_THRESHOLD_MM - 0.01)
    assert all(not r.precipitation_flag for r in rows)


def test_precipitation_flag_true_above_threshold(spark: SparkSession, tmp_path):
    rows = _features_for(spark, tmp_path, precipitation=PRECIP_THRESHOLD_MM + 0.1)
    assert all(r.precipitation_flag for r in rows)


def test_wind_category_calm(spark: SparkSession, tmp_path):
    rows = _features_for(spark, tmp_path, windspeed=WIND_CALM_MS - 0.1)
    assert all(r.wind_category == "calm" for r in rows)


def test_wind_category_breeze(spark: SparkSession, tmp_path):
    rows = _features_for(spark, tmp_path, windspeed=(WIND_CALM_MS + WIND_STRONG_MS) / 2)
    assert all(r.wind_category == "breeze" for r in rows)


def test_wind_category_strong(spark: SparkSession, tmp_path):
    rows = _features_for(spark, tmp_path, windspeed=WIND_STRONG_MS + 1.0)
    assert all(r.wind_category == "strong" for r in rows)


def test_comfort_score_at_ideal_temperature(spark: SparkSession, tmp_path):
    """T=22 C, no rain, calm wind -> comfort near 100 (only wind penalty applies)."""
    wind_val = 0.5  # m/s
    rows = _features_for(
        spark, tmp_path, temperature=TEMP_IDEAL_C, precipitation=0.0, windspeed=wind_val
    )
    expected = 100.0 - wind_val * WIND_WEIGHT  # no temp deviation, no rain penalty
    for row in rows:
        assert abs(row.comfort_score - expected) < 0.1


def test_comfort_score_clipped_to_zero(spark: SparkSession, tmp_path):
    """Very high temperature + rain + high wind drives score negative -> clipped to 0."""
    rows = _features_for(spark, tmp_path, temperature=50.0, precipitation=5.0, windspeed=20.0)
    assert all(r.comfort_score == 0.0 for r in rows)


def test_comfort_score_max_is_100(spark: SparkSession, tmp_path):
    """Ideal conditions produce comfort <= 100."""
    rows = _features_for(
        spark, tmp_path, temperature=TEMP_IDEAL_C, precipitation=0.0, windspeed=0.0
    )
    assert all(r.comfort_score <= 100.0 for r in rows)


def test_heat_index_reasonable_range(spark: SparkSession, tmp_path):
    """For CDMX-typical temps (10-35 C) heat index stays within a plausible range."""
    rows = _features_for(spark, tmp_path, temperature=22.0, humidity=60.0)
    for row in rows:
        assert 0.0 < row.heat_index < 45.0


def test_heat_index_increases_with_humidity(spark: SparkSession, tmp_path):
    """Heat index at RH=80 should exceed heat index at RH=40 for the same temperature."""
    rows_low = _features_for(spark, tmp_path, temperature=30.0, humidity=40.0)
    rows_high = _features_for(spark, tmp_path, temperature=30.0, humidity=80.0)
    hi_low = rows_low[0].heat_index
    hi_high = rows_high[0].heat_index
    assert hi_high > hi_low, f"Expected hi@RH80 > hi@RH40, got {hi_high:.2f} vs {hi_low:.2f}"


# ---------------------------------------------------------------------------
# _transform (end-to-end) tests
# ---------------------------------------------------------------------------


def test_transform_output_schema(spark: SparkSession, tmp_path):
    """_transform output has obs_timestamp, service_date, avg_*, and feature columns."""
    glob = _write_fixture(tmp_path)
    df = _transform(spark, glob)
    required = {
        "obs_timestamp",
        "service_date",
        "avg_temperature_2m",
        "avg_precipitation",
        "heat_index",
        "comfort_score",
        "precipitation_flag",
        "wind_category",
    }
    assert required.issubset(set(df.columns))


def test_transform_service_date_from_utc_string(spark: SparkSession, tmp_path):
    """service_date is the UTC date from obs_time, not CDMX-local."""
    glob = _write_fixture(tmp_path)  # times are "2026-04-19T00:00" and "2026-04-19T01:00"
    df = _transform(spark, glob)
    dates = {str(r.service_date) for r in df.collect()}
    assert dates == {"2026-04-19"}


def test_transform_row_count(spark: SparkSession, tmp_path):
    """One row per UTC hour in the file."""
    glob = _write_fixture(tmp_path)
    df = _transform(spark, glob)
    assert df.count() == _N_HOURS
