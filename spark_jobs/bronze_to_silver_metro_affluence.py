"""Metro affluence Bronze → Silver transformation.

Reads afluenciastc_simple_*.csv from the Bronze layer, fixes double-encoded
UTF-8, canonicalizes station names, and writes a daily Parquet dataset to Silver.

Schema correction vs Phase 2 plan
----------------------------------
The plan assumed the CSVs have a wide format with 96 x 15-minute time-slot
columns (00:00, 00:15, …, 23:45) requiring a wide→long stack transform. The
actual CDMX CKAN dataset (afluencia-diaria-del-metro-cdmx) contains DAILY totals
only — one row per (fecha, linea, estacion). The output table is named
affluence_daily rather than affluence_hourly; the stack operation is omitted.

Encoding
--------
Both CSV vintages store accented characters as doubly-encoded UTF-8. Original
UTF-8 bytes (e.g. á = 0xC3 0xA1) were misread as Latin-1 and re-encoded as UTF-8,
producing 4 bytes per accented char (0xC3 0x83 0xC2 0xA1 for á). Some post-2020
rows are correctly single-encoded UTF-8. The fix_encoding UDF handles both cases:
it attempts the Latin-1 → UTF-8 reversal and falls back to the original string
when that round-trip fails (which is the case for already-clean strings).

Bucket note
-----------
The metro ingestor writes to gs://cdmx-mobility-raw/ (the Settings.raw_bucket_name
default). The Terraform-provisioned data bucket is cdmx-mobility-data. Silver
output goes to cdmx-mobility-data/silver/ to keep all Silver data co-located.

Inputs
------
  Bronze: gs://cdmx-mobility-raw/metro/affluence/
          ingestion_date=*/afluenciastc_simple_*.csv
  Columns: fecha (YYYY-MM-DD), anio, mes, linea, estacion, afluencia

Outputs
-------
  Silver: gs://cdmx-mobility-data/silver/metro/affluence_daily/
          partitioned by service_date (DATE)
  Columns: service_date, linea, station_raw, station_canonical, daily_entries
"""

import click
from google.cloud import storage as gcs
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, to_date, udf
from pyspark.sql.types import IntegerType, StringType

from ingestion.bq_logger import IngestionLogger, RunResult
from ingestion.config import Settings
from spark_jobs.conformance.spark_session import get_spark_session
from spark_jobs.conformance.station_names import canonicalize_station_udf

_RAW_BUCKET = "cdmx-mobility-raw"
_DATA_BUCKET = "cdmx-mobility-data"

DEFAULT_INPUT_PATH = (
    f"gs://{_RAW_BUCKET}/metro/affluence/ingestion_date=*/afluenciastc_simple_*.csv"
)
DEFAULT_OUTPUT_PATH = f"gs://{_DATA_BUCKET}/silver/metro/affluence_daily/"


def _fix_encoding(s: str | None) -> str | None:
    """Reverse double-encoded UTF-8 mojibake present in both afluenciastc CSV vintages.

    The reversal: encode the garbled string back to Latin-1 (recovering the
    original UTF-8 bytes), then decode those bytes as UTF-8.

    Correctly-encoded strings (post-2020 rows, pure-ASCII values) cannot encode
    to Latin-1 without error, so the try/except preserves them unchanged.
    """
    if s is None:
        return None
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


_fix_encoding_udf = udf(_fix_encoding, StringType())


def _transform(spark: SparkSession, input_path: str) -> DataFrame:
    # 1. Read all CSVs with all-string schema.
    #    PERMISSIVE mode (default) turns malformed rows into nulls rather than failing.
    raw = (
        spark.read.option("header", True)
        .option("encoding", "UTF-8")
        .option("mode", "PERMISSIVE")
        .csv(input_path)
    )
    # Expected schema: fecha, anio, mes, linea, estacion, afluencia (all StringType)

    # 2. Fix double-encoded UTF-8 on every text column that may contain accents.
    #    linea  → e.g. "LÃ­nea 1"   → "Línea 1"
    #    estacion → e.g. "PantitlÃ¡n" → "Pantitlán"
    fixed = raw.withColumn("linea", _fix_encoding_udf(col("linea"))).withColumn(
        "estacion", _fix_encoding_udf(col("estacion"))
    )

    # 3. Canonicalize station names.
    #    Keep the raw value for auditability; add a canonical column for joins.
    canonicalized = fixed.withColumnRenamed("estacion", "station_raw").withColumn(
        "station_canonical", canonicalize_station_udf(col("station_raw"))
    )

    # 4. Parse date and cast numeric columns.
    #    anio and mes are redundant with service_date — drop them.
    #    afluencia is occasionally empty or "-" in older vintages; cast to INT so
    #    invalid values become null and are filtered in the next step.
    typed = (
        canonicalized.withColumn("service_date", to_date(col("fecha"), "yyyy-MM-dd"))
        .withColumn("daily_entries", col("afluencia").cast(IntegerType()))
        .drop("fecha", "anio", "mes", "afluencia")
    )

    # 5. Drop rows where parsing failed.
    clean = typed.filter(col("service_date").isNotNull() & col("daily_entries").isNotNull())

    return clean


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
    result = RunResult(source="spark_metro_affluence")
    bq_logger = IngestionLogger(project_id=gcp_project_id)

    try:
        df = _transform(spark, input_path)

        # Cache before count so the DAG is executed once, not twice.
        df.cache()
        row_count = df.count()

        # 6. Repartition so each service_date partition has exactly one output file.
        #    repartition(col) hash-partitions all rows for the same date into the
        #    same shuffle partition. With ~5 840 distinct dates and 200 shuffle
        #    partitions, several dates share one partition, but each still produces
        #    exactly one Parquet file per output directory.
        #    Without this, the default 200 shuffle partitions produce up to 200
        #    tiny part-*.parquet files inside every service_date= directory.
        df = df.repartition(col("service_date"))

        # 7. Write Silver Parquet.
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
    help="GCS glob or local path for input CSVs",
)
@click.option(
    "--output-path",
    default=DEFAULT_OUTPUT_PATH,
    show_default=True,
    help="GCS or local path for Silver Parquet output",
)
@click.option(
    "--local",
    is_flag=True,
    help="Run with local[2] master for smoke-testing (no cluster needed)",
)
def run(input_path: str, output_path: str, local: bool) -> None:
    """Transform metro affluence Bronze CSVs to Silver Parquet (daily totals)."""
    settings = Settings()
    spark = get_spark_session("cdmx-metro-affluence-silver", local=local)
    try:
        run_job(spark, input_path, output_path, settings.gcp_project_id)
    finally:
        spark.stop()


if __name__ == "__main__":
    run()
