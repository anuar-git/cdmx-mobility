"""Weather Bronze -> Silver transformation.

Reads Open-Meteo NDJSON weather files from Bronze, pivots from columnar array
format (one row per coordinate with hourly arrays) to one row per hour with a
column per coordinate, then adds city-wide averages and derived comfort features.

Input format (NDJSON -- one JSON line per coordinate per file):
  coordinate_id, latitude, longitude, fetch_date,
  hourly: { time[], temperature_2m[], precipitation[], windspeed_10m[], relativehumidity_2m[] }

Output schema (one row per UTC hour):
  obs_timestamp (TIMESTAMP), service_date (DATE),
  -- per-coordinate columns (5 x 4 = 20) --
  centro_temperature_2m, centro_precipitation, centro_windspeed_10m,
  centro_relativehumidity_2m, aeropuerto_* ... ecatepec_*,
  -- city-wide averages (4) --
  avg_temperature_2m, avg_precipitation, avg_windspeed_10m, avg_relativehumidity_2m,
  -- derived features (4) --
  heat_index, comfort_score, precipitation_flag, wind_category

Derived feature formulas
------------------------
heat_index (Celsius):
  Uses the NOAA/NWS Rothfusz regression for heat index, applied to the
  city-wide average temperature and relative humidity. A two-step approach:
    1. Compute the simple heat index (Steadman):
       HI_simple = 0.5 * (T_F + 61 + (T_F - 68) * 1.2 + RH * 0.094)
    2. If HI_simple < 80 F, use it directly; otherwise apply the full
       Rothfusz regression (more accurate at high T + high RH combinations).
  Result is converted back to Celsius. At CDMX altitudes (~2240 m), felt
  temperatures rarely exceed 30 C so the simple formula dominates.

comfort_score (0-100):
  score = 100
        - |T_avg - TEMP_IDEAL_C| * TEMP_WEIGHT     # temperature deviation penalty
        - precipitation_flag * PRECIP_PENALTY       # rain penalty
        - windspeed_avg * WIND_WEIGHT               # wind penalty
  Clipped to [0, 100].
  Constants: TEMP_IDEAL_C = 22 C, TEMP_WEIGHT = 3 pt/C,
             PRECIP_PENALTY = 20 pt, WIND_WEIGHT = 1.5 pt/(m/s).

precipitation_flag (BOOLEAN): avg_precipitation > PRECIP_THRESHOLD_MM (0.1 mm).

wind_category (STRING): Beaufort-scale approximation in m/s.
  calm   -- windspeed < WIND_CALM_MS  (1.5 m/s, Beaufort 0-1)
  breeze -- 1.5 <= windspeed < WIND_STRONG_MS (10.7 m/s, Beaufort 1-5)
  strong -- windspeed >= 10.7 m/s (Beaufort 6+)

service_date note
-----------------
Open-Meteo times are UTC ISO strings ("2026-04-19T00:00"). service_date is
derived from the UTC date portion of obs_timestamp, keeping all 24 hours of a
UTC fetch-day in the same partition. This avoids splitting a single weather
file across two CDMX-local dates (hours 00-05 UTC = 18-23 CDMX CST).

Inputs
------
  Bronze: gs://cdmx-mobility-data/weather/hourly/ingestion_date=*/weather_*.json

Outputs
-------
  Silver: gs://cdmx-mobility-data/silver/weather/hourly_fact/
          partitioned by service_date (DATE)
"""

from functools import reduce
from operator import add

import click
import structlog
from google.cloud import storage as gcs
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import abs as spark_abs
from pyspark.sql.functions import (
    arrays_zip,
    col,
    explode,
    first,
    lit,
    to_date,
    to_timestamp,
    when,
)

from ingestion.bq_logger import IngestionLogger, RunResult
from spark_jobs.conformance.spark_session import get_spark_session

log = structlog.get_logger()

_BUCKET = "cdmx-mobility-data"
DEFAULT_INPUT_PATH = f"gs://{_BUCKET}/weather/hourly/ingestion_date=*/weather_*.json"
DEFAULT_OUTPUT_PATH = f"gs://{_BUCKET}/silver/weather/hourly_fact/"

# Must match coordinate IDs produced by ingestion/weather/openmeteo.py.
COORDINATE_IDS: list[str] = [
    "centro",
    "aeropuerto",
    "pedregal",
    "tlalnepantla",
    "ecatepec",
]

# ── Derived feature constants ────────────────────────────────────────────────

TEMP_IDEAL_C: float = 22.0  # comfort reference temperature (°C)
TEMP_WEIGHT: float = 3.0  # comfort penalty per °C deviation
PRECIP_PENALTY: float = 20.0  # comfort penalty when it rains
WIND_WEIGHT: float = 1.5  # comfort penalty per m/s of wind
PRECIP_THRESHOLD_MM: float = 0.1  # minimum precipitation to set the flag
WIND_CALM_MS: float = 1.5  # upper bound for "calm" (Beaufort 0-1)
WIND_STRONG_MS: float = 10.7  # lower bound for "strong" (Beaufort 6+)

# ISO format used by Open-Meteo hourly timestamps ("2026-04-19T00:00").
_OPENMETEO_TIME_FMT = "yyyy-MM-dd'T'HH:mm"


def _load_hourly(spark: SparkSession, input_path: str) -> DataFrame:
    """Read NDJSON weather files and explode hourly arrays to one row per (coord, hour).

    Open-Meteo returns parallel arrays for each hourly variable. `arrays_zip`
    stitches them into an array of per-hour structs so `explode` produces one
    flat row per observation.
    """
    raw = spark.read.json(input_path)

    with_named = raw.select(
        col("coordinate_id"),
        col("hourly.time").alias("time_arr"),
        col("hourly.temperature_2m").alias("temp_arr"),
        col("hourly.precipitation").alias("precip_arr"),
        col("hourly.windspeed_10m").alias("wind_arr"),
        col("hourly.relativehumidity_2m").alias("humidity_arr"),
    )

    with_zipped = with_named.withColumn(
        "hourly_rows",
        arrays_zip(
            col("time_arr"),
            col("temp_arr"),
            col("precip_arr"),
            col("wind_arr"),
            col("humidity_arr"),
        ),
    )

    return with_zipped.select(col("coordinate_id"), explode("hourly_rows").alias("hr")).select(
        col("coordinate_id"),
        col("hr.time_arr").alias("obs_time"),
        col("hr.temp_arr").alias("temperature_2m"),
        col("hr.precip_arr").alias("precipitation"),
        col("hr.wind_arr").alias("windspeed_10m"),
        col("hr.humidity_arr").alias("relativehumidity_2m"),
    )


def _pivot_by_coordinate(df: DataFrame) -> DataFrame:
    """Pivot from one row per (coordinate, hour) to one row per hour.

    After pivot the column names are {coordinate_id}_{metric}, e.g.
    `centro_temperature_2m`, `aeropuerto_precipitation`, etc.
    Specifying COORDINATE_IDS explicitly avoids a full-data scan to discover
    pivot values and produces deterministic column ordering.
    """
    return (
        df.groupBy("obs_time")
        .pivot("coordinate_id", COORDINATE_IDS)
        .agg(
            first("temperature_2m").alias("temperature_2m"),
            first("precipitation").alias("precipitation"),
            first("windspeed_10m").alias("windspeed_10m"),
            first("relativehumidity_2m").alias("relativehumidity_2m"),
        )
    )


def _city_wide_averages(df: DataFrame) -> DataFrame:
    """Add avg_* columns as the arithmetic mean across all coordinate columns."""

    def _avg(suffix: str):
        cols = [col(f"{c}_{suffix}") for c in COORDINATE_IDS]
        return reduce(add, cols) / len(COORDINATE_IDS)

    return (
        df.withColumn("avg_temperature_2m", _avg("temperature_2m"))
        .withColumn("avg_precipitation", _avg("precipitation"))
        .withColumn("avg_windspeed_10m", _avg("windspeed_10m"))
        .withColumn("avg_relativehumidity_2m", _avg("relativehumidity_2m"))
    )


def _add_derived_features(df: DataFrame) -> DataFrame:
    """Compute heat_index, comfort_score, precipitation_flag, wind_category.

    All formulas are pure Spark Column expressions (no UDFs) — they execute
    natively on the JVM and avoid Python serialisation overhead.
    """
    t_c = col("avg_temperature_2m")
    rh = col("avg_relativehumidity_2m")
    w = col("avg_windspeed_10m")

    # Heat index (Rothfusz regression, NWS) -- convert C to F, compute, convert back.
    t_f = t_c * lit(9.0 / 5.0) + lit(32.0)

    # Simple Steadman formula -- accurate for HI_F < 80 F.
    hi_simple = lit(0.5) * (t_f + lit(61.0) + (t_f - lit(68.0)) * lit(1.2) + rh * lit(0.094))

    # Full Rothfusz regression -- accurate for HI_F >= 80 F (hot + humid).
    hi_full = (
        lit(-42.379)
        + lit(2.04901523) * t_f
        + lit(10.14333127) * rh
        - lit(0.22475541) * t_f * rh
        - lit(0.00683783) * t_f * t_f
        - lit(0.05481717) * rh * rh
        + lit(0.00122874) * t_f * t_f * rh
        + lit(0.00085282) * t_f * rh * rh
        - lit(0.00000199) * t_f * t_f * rh * rh
    )

    hi_f = when(hi_simple < lit(80.0), hi_simple).otherwise(hi_full)
    heat_index = (hi_f - lit(32.0)) * lit(5.0 / 9.0)

    # Precipitation flag
    precipitation_flag = col("avg_precipitation") > lit(PRECIP_THRESHOLD_MM)

    # Wind category (Beaufort-scale approximation in m/s)
    wind_category = (
        when(lit(WIND_CALM_MS) > w, lit("calm"))
        .when(lit(WIND_STRONG_MS) > w, lit("breeze"))
        .otherwise(lit("strong"))
    )

    # Comfort score (0-100)
    raw_score = (
        lit(100.0)
        - spark_abs(t_c - lit(TEMP_IDEAL_C)) * lit(TEMP_WEIGHT)
        - when(precipitation_flag, lit(PRECIP_PENALTY)).otherwise(lit(0.0))
        - w * lit(WIND_WEIGHT)
    )
    comfort_score = (
        when(raw_score < lit(0.0), lit(0.0))
        .when(raw_score > lit(100.0), lit(100.0))
        .otherwise(raw_score)
    )

    return (
        df.withColumn("heat_index", heat_index)
        .withColumn("precipitation_flag", precipitation_flag)
        .withColumn("wind_category", wind_category)
        .withColumn("comfort_score", comfort_score)
    )


def _transform(spark: SparkSession, input_path: str) -> DataFrame:
    hourly = _load_hourly(spark, input_path)
    pivoted = _pivot_by_coordinate(hourly)
    with_avgs = _city_wide_averages(pivoted)
    with_features = _add_derived_features(with_avgs)

    # Parse obs_time string → TimestampType; derive service_date from UTC date
    # portion only (avoids splitting a fetch-day file across two CDMX dates).
    return (
        with_features.withColumn(
            "obs_timestamp", to_timestamp(col("obs_time"), _OPENMETEO_TIME_FMT)
        )
        .withColumn("service_date", to_date(col("obs_time"), _OPENMETEO_TIME_FMT))
        .drop("obs_time")
    )


def _silver_stats(output_path: str) -> tuple[int, int]:
    """Return (file_count, byte_count) for the just-written Silver prefix.

    Returns (0, 0) for local paths (--local smoke-test mode).
    """
    if not output_path.startswith("gs://"):
        return 0, 0
    bucket_name, prefix = output_path.replace("gs://", "").split("/", 1)
    client = gcs.Client()
    blobs = list(client.list_blobs(bucket_name, prefix=prefix))
    return len(blobs), sum(b.size for b in blobs)


def run_job(
    spark: SparkSession,
    input_path: str,
    output_path: str,
    gcp_project_id: str,
) -> RunResult:
    result = RunResult(source="spark_weather_silver")
    bq_logger = IngestionLogger(project_id=gcp_project_id)

    try:
        df = _transform(spark, input_path)

        df.cache()
        row_count = df.count()
        log.info("weather_rows", row_count=row_count)

        df = df.repartition(col("service_date"))
        (df.write.partitionBy("service_date").mode("overwrite").parquet(output_path))
        df.unpersist()

        file_count, byte_count = _silver_stats(output_path)
        result.file_count = file_count
        result.byte_count = byte_count
        result.row_count = row_count

    except Exception as exc:
        result.status = "error"
        result.error_message = str(exc)
        raise

    finally:
        bq_logger.log(result)

    return result


@click.command()
@click.option(
    "--input-path",
    default=DEFAULT_INPUT_PATH,
    show_default=True,
    help="GCS glob for Bronze weather NDJSON files",
)
@click.option(
    "--output-path",
    default=DEFAULT_OUTPUT_PATH,
    show_default=True,
    help="GCS or local path for Silver hourly_fact Parquet output",
)
@click.option(
    "--local",
    is_flag=True,
    help="Run with local[2] master for smoke-testing (no cluster needed)",
)
@click.option(
    "--gcp-project-id",
    envvar="CDMX_GCP_PROJECT_ID",
    required=True,
    help="GCP project ID (or set CDMX_GCP_PROJECT_ID)",
)
def run(input_path: str, output_path: str, local: bool, gcp_project_id: str) -> None:
    """Transform Open-Meteo weather NDJSON to Silver hourly_fact Parquet."""
    spark = get_spark_session("cdmx-weather-silver", local=local)
    try:
        run_job(spark, input_path, output_path, gcp_project_id)
    finally:
        spark.stop()


if __name__ == "__main__":
    run()
