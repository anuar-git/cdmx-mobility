"""Metrobús Bronze → Silver transformation — stop dwell events.

Reads GTFS-RT vehicle position NDJSON snapshots and the latest Metrobús stops
feed from Bronze, snaps each position to its nearest stop via H3 indexing, then
collapses contiguous at-stop observations into dwell events.

NDJSON schema note
------------------
`spark.read.json()` infers the `vehicle` field as a StructType (nested JSON
object from the GTFS-RT FeedEntity). The BigQuery external table declares the
same column as the JSON type, but both derive from the same nested NDJSON
object written by `MessageToDict(preserving_proto_field_name=True)`. Spark
struct accessors (`col("vehicle.vehicle.id")`) are used instead of
get_json_object — they are equivalent in meaning but avoid the BQ-specific JSON
path syntax.

Stop snapping
-------------
Metrobús system: ~312 stops, ~300 active vehicles.
After the inbound webhook is live, positions arrive in ~2-min batches
(~720 snapshots/day x ~300 vehicles = ~216K position rows/day).
snap_to_nearest_stop joins on exact H3 cell match (resolution 9, ~174m
hexagons); most positions between stops have no match and are dropped by
the inner join. Only positions within ~174m of a stop are retained.

Dwell event detection
---------------------
A dwell event is a contiguous sequence of position reports for a given
vehicle at the same stop, separated by no more than SESSION_GAP_SECONDS (60s).
Sessions shorter than MIN_DWELL_SECONDS (30s) are drive-by observations and
are discarded.

Implementation: within each (vehicle_id, stop_id) window ordered by timestamp,
lag() provides the previous timestamp; a new session starts when the gap exceeds
SESSION_GAP_SECONDS or when there is no previous record. A cumulative sum of
session-start flags assigns a monotonically increasing session_id per
(vehicle_id, stop_id) partition, which is used as the groupBy key before being
dropped from the output.

Inputs
------
  Positions: gs://cdmx-mobility-data/metrobus/vehicle_positions/
             ingestion_date=*/   (NDJSON, one entity per line)
  Stops:     gs://cdmx-mobility-data/metrobus/static/stops/
             ingestion_date=*/stops.csv  (only the most recent partition is used)

Outputs
-------
  Silver: gs://cdmx-mobility-data/silver/metrobus/stop_events/
          partitioned by service_date (DATE) and route_id (STRING)
  Columns: vehicle_id, trip_id, route_id, stop_id, stop_name, stop_sequence,
           dwell_start_ts, dwell_end_ts, dwell_seconds, service_date
"""

import click
import structlog
from google.cloud import storage as gcs
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    col,
    first,
    from_unixtime,
    input_file_name,
    lag,
    lit,
    regexp_extract,
    unix_timestamp,
    when,
)
from pyspark.sql.functions import max as spark_max
from pyspark.sql.functions import min as spark_min
from pyspark.sql.functions import sum as spark_sum
from pyspark.sql.types import DoubleType, IntegerType, TimestampType
from pyspark.sql.window import Window

from ingestion.bq_logger import IngestionLogger, RunResult
from spark_jobs.conformance.h3_utils import lat_lon_to_h3_udf, snap_to_nearest_stop
from spark_jobs.conformance.spark_session import get_spark_session
from spark_jobs.conformance.time_utils import extract_service_date

log = structlog.get_logger()

_BUCKET = "cdmx-mobility-data"

DEFAULT_POSITIONS_INPUT = f"gs://{_BUCKET}/metrobus/vehicle_positions/ingestion_date=*/"
DEFAULT_STOPS_INPUT = f"gs://{_BUCKET}/metrobus/static/stops/ingestion_date=*/stops.csv"
DEFAULT_OUTPUT_PATH = f"gs://{_BUCKET}/silver/metrobus/stop_events/"


def _positions_input_for_date(input_date: str | None) -> str:
    """Return a date-scoped positions glob when input_date is given."""
    if input_date:
        return f"gs://{_BUCKET}/metrobus/vehicle_positions/ingestion_date={input_date}/"
    return DEFAULT_POSITIONS_INPUT


# A gap larger than this (seconds) between consecutive at-stop records breaks
# the session and starts a new dwell event for that vehicle+stop pair.
# sinopticoplus delivers snapshots every ~5 minutes (300s); set the threshold
# above that so consecutive same-stop readings form a single session.
SESSION_GAP_SECONDS: int = 600

# Dwell events shorter than this are drive-by observations; they are dropped.
# With ~5-minute snapshot intervals, any detected dwell is at least 300s;
# this threshold just guards against single-reading edge cases.
MIN_DWELL_SECONDS: int = 30


def _load_positions(spark: SparkSession, input_path: str) -> DataFrame:
    """Read NDJSON vehicle positions, flatten fields, and attach H3 cell index.

    Drops rows where latitude or longitude is null — these cannot be snapped to
    a stop and contribute nothing to dwell event detection.
    """
    raw = spark.read.json(input_path)

    flattened = (
        raw.filter(col("vehicle").isNotNull())
        .select(
            col("id").alias("entity_id"),
            col("vehicle.vehicle.id").alias("vehicle_id"),
            col("vehicle.vehicle.label").alias("vehicle_label"),
            col("vehicle.trip.route_id").alias("route_id"),
            # sinopticoplus omits trip_id, current_stop_sequence, current_status
            lit(None).cast("string").alias("trip_id"),
            lit(None).cast(IntegerType()).alias("stop_sequence"),
            col("vehicle.position.latitude").cast(DoubleType()).alias("latitude"),
            col("vehicle.position.longitude").cast(DoubleType()).alias("longitude"),
            lit(None).cast("string").alias("current_status"),
            # vehicle.timestamp is epoch seconds as a string; direct cast to
            # TimestampType returns null in Spark 3 — use from_unixtime instead.
            from_unixtime(col("vehicle.timestamp")).cast(TimestampType()).alias("timestamp"),
        )
        .filter(col("latitude").isNotNull() & col("longitude").isNotNull())
    )

    return flattened.withColumn("position_h3", lat_lon_to_h3_udf(col("latitude"), col("longitude")))


def _load_stops(spark: SparkSession, input_path: str) -> DataFrame:
    """Read Metrobús stops from all ingestion_date partitions; return the latest.

    Multiple ingestion_date partitions may exist. The partition date is extracted
    from the file path via input_file_name() + regex so that the function works
    identically against GCS paths and local tmp_path fixtures in tests.
    """
    raw = (
        spark.read.option("header", True)
        .csv(input_path)
        .withColumn("_file", input_file_name())
        .withColumn(
            "_partition_date",
            regexp_extract(col("_file"), r"ingestion_date=(\d{4}-\d{2}-\d{2})", 1),
        )
    )

    max_date = raw.agg(spark_max("_partition_date")).collect()[0][0]

    latest = (
        raw.filter(col("_partition_date") == max_date)
        .filter(col("stop_id").isNotNull())
        .select(
            col("stop_id"),
            col("stop_name"),
            col("stop_lat").cast(DoubleType()).alias("stop_lat"),
            col("stop_lon").cast(DoubleType()).alias("stop_lon"),
        )
    )

    return latest.withColumn("stop_h3", lat_lon_to_h3_udf(col("stop_lat"), col("stop_lon")))


def _compute_dwell_events(snapped: DataFrame) -> DataFrame:
    """Collapse contiguous at-stop observations into dwell events.

    Algorithm:
      1. Within each (vehicle_id, stop_id) window ordered by timestamp, compute
         the gap to the previous record via lag(timestamp).
      2. Mark a new session when the gap exceeds SESSION_GAP_SECONDS or when
         there is no prior record (first appearance at this stop).
      3. Assign a session_id as the cumulative sum of session-start flags; this
         monotonically increases within each (vehicle_id, stop_id) partition.
      4. Aggregate each session: min/max timestamp, first route/trip/stop_seq.
      5. Compute dwell_seconds and discard sessions under MIN_DWELL_SECONDS.
      6. Add service_date (CDMX-local date) derived from dwell_start_ts.
    """
    w = Window.partitionBy("vehicle_id", "stop_id").orderBy("timestamp")
    w_cumsum = w.rowsBetween(Window.unboundedPreceding, 0)

    with_session = (
        snapped.withColumn("_prev_ts", lag("timestamp", 1).over(w))
        .withColumn(
            "_gap_seconds",
            when(
                col("_prev_ts").isNull(),
                lit(0),
            ).otherwise(unix_timestamp(col("timestamp")) - unix_timestamp(col("_prev_ts"))),
        )
        .withColumn(
            "_is_new_session",
            when(
                col("_prev_ts").isNull() | (col("_gap_seconds") > SESSION_GAP_SECONDS),
                lit(1),
            ).otherwise(lit(0)),
        )
        .withColumn("_session_id", spark_sum("_is_new_session").over(w_cumsum))
    )

    dwell_raw = (
        with_session.groupBy("vehicle_id", "stop_id", "stop_name", "_session_id")
        .agg(
            spark_min(col("timestamp")).alias("dwell_start_ts"),
            spark_max(col("timestamp")).alias("dwell_end_ts"),
            first(col("route_id"), ignorenulls=True).alias("route_id"),
            first(col("trip_id"), ignorenulls=True).alias("trip_id"),
            first(col("stop_sequence"), ignorenulls=True).alias("stop_sequence"),
        )
        .withColumn(
            "dwell_seconds",
            (unix_timestamp(col("dwell_end_ts")) - unix_timestamp(col("dwell_start_ts"))).cast(
                IntegerType()
            ),
        )
        .filter(col("dwell_seconds") >= MIN_DWELL_SECONDS)
        .drop("_session_id")
    )

    return dwell_raw.withColumn("service_date", extract_service_date("dwell_start_ts"))


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
    stops_input: str,
    output_path: str,
    gcp_project_id: str,
) -> RunResult:
    result = RunResult(source="spark_metrobus_stop_events")
    bq_logger = IngestionLogger(project_id=gcp_project_id)

    try:
        positions = _load_positions(spark, input_path)

        stops = _load_stops(spark, stops_input)
        # Pass only the columns needed for snap; stop_lat/stop_lon are dropped
        # to avoid unused columns in the snapped DataFrame.
        stops_for_snap = stops.select("stop_id", "stop_name", "stop_h3")

        log.info("snapping_positions_to_stops")
        snapped = snap_to_nearest_stop(
            positions_df=positions,
            stops_df=stops_for_snap,
            position_h3_col="position_h3",
            stop_h3_col="stop_h3",
            max_h3_distance=2,
        )
        log.info("snapped_row_count", row_count=snapped.count())

        df = _compute_dwell_events(snapped)

        # Cache before count so the window + groupBy DAG is executed once.
        df.cache()
        row_count = df.count()

        log.info("dwell_events_computed", row_count=row_count)

        df = df.repartition(col("service_date"), col("route_id"))
        (df.write.partitionBy("service_date", "route_id").mode("overwrite").parquet(output_path))
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
    default=None,
    help="GCS glob for vehicle position NDJSON files (overrides --input-date)",
)
@click.option(
    "--input-date",
    default=None,
    help="Process only this ingestion_date partition (YYYY-MM-DD). "
    "Ignored when --input-path is set explicitly.",
)
@click.option(
    "--stops-input",
    default=DEFAULT_STOPS_INPUT,
    show_default=True,
    help="GCS glob for Metrobús stops CSVs (all partitions; latest is used)",
)
@click.option(
    "--output-path",
    default=DEFAULT_OUTPUT_PATH,
    show_default=True,
    help="GCS or local path for Silver stop_events Parquet output",
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
    stops_input: str,
    output_path: str,
    local: bool,
    gcp_project_id: str,
) -> None:
    """Transform Metrobús vehicle positions to Silver stop-dwell events."""
    resolved_input = input_path or _positions_input_for_date(input_date)
    spark = get_spark_session("cdmx-metrobus-stop-events-silver", local=local)
    try:
        run_job(spark, resolved_input, stops_input, output_path, gcp_project_id)
    finally:
        spark.stop()


if __name__ == "__main__":
    run()
