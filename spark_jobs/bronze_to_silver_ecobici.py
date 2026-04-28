"""EcoBici Bronze → Silver transformation.

Reads station_status GBFS JSON snapshots from Bronze, explodes the stations
array, deduplicates consecutive identical states per station using a window
function, and writes two Silver datasets:

  1. silver/ecobici/state_changes/  — deduplicated state-change events,
     partitioned by service_date (DATE, CDMX-local).
  2. silver/ecobici/station_master/ — latest station_information snapshot,
     one Parquet file, no partitioning.

Deduplication rationale
-----------------------
The EcoBici ingestor polls every 2 minutes (~720 snapshots/day, ~470 stations
= ~340K rows/day). Most consecutive snapshots per station are identical — no
bike was hired or returned. The windowed lag() filter retains only rows where
at least one field changed, compressing ~340K to ~50-80K rows/day (~6-9x)
with no information loss: any downstream aggregation can reconstruct the full
timeline by forward-filling the state-change rows.

Snapshot timestamp
------------------
The GBFS envelope's `last_updated` field (epoch seconds) is the authoritative
snapshot timestamp. It is cast to TimestampType directly; no division by 1000
is needed because GBFS timestamps are seconds, not milliseconds.

station_master
--------------
station_information is near-static (stations rarely open or close). The Silver
job overwrites station_master on every run with the single most recent
ingestion_date snapshot. This keeps the table tiny and always current, and
matches the ECOBICI_STATION_MASTER_PATH constant in conformance/station_names.py.

Inputs
------
  Bronze status:  gs://cdmx-mobility-data/ecobici/station_status/
                  ingestion_ts=*/station_status.json
  Bronze info:    gs://cdmx-mobility-data/ecobici/station_information/
                  ingestion_date=*/station_information.json

Outputs
-------
  Silver state_changes: gs://cdmx-mobility-data/silver/ecobici/state_changes/
      Columns: snapshot_ts, station_id, num_bikes_available,
               num_docks_available, is_renting, is_returning,
               last_reported, service_date
  Silver station_master: gs://cdmx-mobility-data/silver/ecobici/station_master/
      Columns: station_id, name, lat, lon, capacity
"""

import click
import structlog
from google.cloud import storage as gcs
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, explode, lag
from pyspark.sql.functions import max as spark_max
from pyspark.sql.types import IntegerType, TimestampType
from pyspark.sql.window import Window

from ingestion.bq_logger import IngestionLogger, RunResult
from spark_jobs.conformance.spark_session import get_spark_session
from spark_jobs.conformance.time_utils import extract_service_date

log = structlog.get_logger()

_BUCKET = "cdmx-mobility-data"

DEFAULT_STATUS_INPUT = f"gs://{_BUCKET}/ecobici/station_status/ingestion_ts=*/station_status.json"
DEFAULT_INFO_INPUT = (
    f"gs://{_BUCKET}/ecobici/station_information/ingestion_date=*/station_information.json"
)
DEFAULT_STATE_CHANGES_OUTPUT = f"gs://{_BUCKET}/silver/ecobici/state_changes/"
DEFAULT_STATION_MASTER_OUTPUT = f"gs://{_BUCKET}/silver/ecobici/station_master/"


def _status_input_for_date(input_date: str | None) -> str:
    """Return a date-scoped status glob when input_date is given."""
    if input_date:
        # EcoBici uses ingestion_ts=YYYY-MM-DDTHH-MM — probe the date prefix.
        return (
            f"gs://{_BUCKET}/ecobici/station_status/ingestion_ts={input_date}T*/station_status.json"
        )
    return DEFAULT_STATUS_INPUT


def _info_input_for_date(input_date: str | None) -> str:
    """Return a date-scoped info glob when input_date is given."""
    if input_date:
        return (
            f"gs://{_BUCKET}/ecobici/station_information/"
            f"ingestion_date={input_date}/station_information.json"
        )
    return DEFAULT_INFO_INPUT


def _transform_state_changes(spark: SparkSession, input_path: str) -> DataFrame:
    """Explode station_status snapshots and filter to state-change rows only.

    Reads all snapshot files matching input_path, explodes the data.stations
    array, then uses a lag() window function to keep only rows where at least
    one observable field changed since the previous snapshot for that station.
    The first snapshot per station is always kept (no prior value to compare).
    """
    raw = spark.read.option("multiline", "true").json(input_path)

    # One row per (snapshot, station). last_updated is epoch seconds → TimestampType.
    exploded = raw.select(
        col("last_updated").cast(TimestampType()).alias("snapshot_ts"),
        explode(col("data.stations")).alias("station"),
    ).select(
        col("snapshot_ts"),
        col("station.station_id").alias("station_id"),
        col("station.num_bikes_available").cast(IntegerType()).alias("num_bikes_available"),
        col("station.num_docks_available").cast(IntegerType()).alias("num_docks_available"),
        col("station.is_renting").cast(IntegerType()).alias("is_renting"),
        col("station.is_returning").cast(IntegerType()).alias("is_returning"),
        # last_reported is per-station epoch seconds (when the station last pushed data).
        col("station.last_reported").cast(TimestampType()).alias("last_reported"),
    )

    # Windowed dedup: compare each row to its predecessor within the same station.
    w = Window.partitionBy("station_id").orderBy("snapshot_ts")

    with_prev = (
        exploded.withColumn("_prev_bikes", lag("num_bikes_available", 1).over(w))
        .withColumn("_prev_docks", lag("num_docks_available", 1).over(w))
        .withColumn("_prev_renting", lag("is_renting", 1).over(w))
        .withColumn("_prev_returning", lag("is_returning", 1).over(w))
    )

    # _prev_bikes IS NULL → first snapshot for this station → always keep.
    # Otherwise keep rows where at least one field differs from the prior snapshot.
    state_changes = with_prev.filter(
        col("_prev_bikes").isNull()
        | (col("num_bikes_available") != col("_prev_bikes"))
        | (col("num_docks_available") != col("_prev_docks"))
        | (col("is_renting") != col("_prev_renting"))
        | (col("is_returning") != col("_prev_returning"))
    ).drop("_prev_bikes", "_prev_docks", "_prev_renting", "_prev_returning")

    return state_changes.withColumn("service_date", extract_service_date("snapshot_ts"))


def _transform_station_master(spark: SparkSession, input_path: str) -> DataFrame:
    """Flatten the most recent station_information snapshot into a station master table.

    Multiple ingestion_date partitions may be present. The most recent snapshot
    is identified by the highest last_updated value across all files. Only that
    snapshot's stations are written — older snapshots are discarded.
    """
    raw = spark.read.option("multiline", "true").json(input_path)

    max_ts = raw.agg(spark_max("last_updated")).collect()[0][0]

    latest = raw.filter(col("last_updated") == max_ts)

    return latest.select(explode(col("data.stations")).alias("station")).select(
        col("station.station_id").alias("station_id"),
        col("station.name").alias("name"),
        col("station.lat").alias("lat"),
        col("station.lon").alias("lon"),
        col("station.capacity").cast(IntegerType()).alias("capacity"),
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
    info_input: str,
    output_path: str,
    gcp_project_id: str,
) -> RunResult:
    base = output_path.rstrip("/")
    state_changes_output = f"{base}/state_changes/"
    station_master_output = f"{base}/station_master/"

    result = RunResult(source="spark_ecobici_silver")
    bq_logger = IngestionLogger(project_id=gcp_project_id)

    try:
        # --- State changes ---
        df = _transform_state_changes(spark, input_path)

        # Cache before count so the window DAG is executed once, not twice.
        df.cache()
        output_rows = df.count()

        # Count raw exploded rows for compression-ratio logging.
        raw_exploded = (
            spark.read.option("multiline", "true")
            .json(input_path)
            .select(explode(col("data.stations")).alias("_s"))
            .count()
        )
        compression = raw_exploded / output_rows if output_rows > 0 else 0.0
        log.info(
            "ecobici_dedup",
            input_rows=raw_exploded,
            output_rows=output_rows,
            compression_ratio=round(compression, 2),
        )

        df = df.repartition(col("service_date"))
        df.write.partitionBy("service_date").mode("overwrite").parquet(state_changes_output)
        df.unpersist()

        sc_files, sc_bytes = _silver_stats(state_changes_output)

        # --- Station master ---
        master_df = _transform_station_master(spark, info_input)
        master_df.write.mode("overwrite").parquet(station_master_output)

        sm_files, sm_bytes = _silver_stats(station_master_output)

        result.file_count = sc_files + sm_files
        result.byte_count = sc_bytes + sm_bytes
        result.row_count = output_rows

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
    default=None,
    help="GCS glob for station_status JSON snapshots (overrides --input-date)",
)
@click.option(
    "--input-date",
    default=None,
    help="Process only this date's snapshots (YYYY-MM-DD). "
    "Ignored when --input-path is set explicitly.",
)
@click.option(
    "--info-input",
    default=None,
    help="GCS glob for station_information JSON snapshots (overrides --input-date for info)",
)
@click.option(
    "--output-path",
    default=f"gs://{_BUCKET}/silver/ecobici/",
    show_default=True,
    help="GCS or local base path; state_changes/ and station_master/ are appended",
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
def run(
    input_path: str | None,
    input_date: str | None,
    info_input: str | None,
    output_path: str,
    local: bool,
    gcp_project_id: str,
) -> None:
    """Transform EcoBici station_status snapshots to Silver state-change Parquet."""
    resolved_input = input_path or _status_input_for_date(input_date)
    resolved_info = info_input or _info_input_for_date(input_date)
    spark = get_spark_session("cdmx-ecobici-silver", local=local)
    try:
        run_job(spark, resolved_input, resolved_info, output_path, gcp_project_id)
    finally:
        spark.stop()


if __name__ == "__main__":
    run()
