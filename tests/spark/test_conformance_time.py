"""Tests for spark_jobs.conformance.time_utils.

Mexico City abolished DST in October 2022 and has been permanently at UTC-6
since then. The April DST test verifies no 25-hour anomaly occurs: two UTC
timestamps 24 hours apart in April must still differ by exactly 24 hours after
conversion to CDMX local time.

Timestamps are constructed from epoch seconds cast to TimestampType to avoid
ambiguity from PySpark's session timezone handling of Python datetime objects.
"""

from datetime import UTC, datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from pyspark.sql.types import LongType, StructField, StructType, TimestampType

from spark_jobs.conformance.time_utils import (
    epoch_ms_to_timestamp,
    extract_service_date,
    to_cdmx_timestamp,
)

_SCHEMA = StructType([StructField("epoch_s", LongType())])


def _ts_df(spark: SparkSession, *epoch_seconds: int):
    """Build a DataFrame with a TimestampType 'ts' column from epoch seconds."""
    return spark.createDataFrame([(e,) for e in epoch_seconds], _SCHEMA).withColumn(
        "ts", col("epoch_s").cast(TimestampType())
    )


def test_to_cdmx_timestamp_winter_offset(spark: SparkSession):
    """2026-01-15 03:00 UTC → 2026-01-14 21:00 CDMX (UTC-6 in January)."""
    epoch = int(datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC).timestamp())
    row = _ts_df(spark, epoch).withColumn("cdmx", to_cdmx_timestamp("ts")).collect()[0]
    assert (row.cdmx.year, row.cdmx.month, row.cdmx.day, row.cdmx.hour) == (2026, 1, 14, 21)


def test_to_cdmx_timestamp_april_still_utc_minus_6(spark: SparkSession):
    """April offset is UTC-6 (no DST since October 2022): 06:00 UTC → 00:00 CDMX."""
    epoch = int(datetime(2026, 4, 5, 6, 0, 0, tzinfo=UTC).timestamp())
    row = _ts_df(spark, epoch).withColumn("cdmx", to_cdmx_timestamp("ts")).collect()[0]
    assert (row.cdmx.year, row.cdmx.month, row.cdmx.day, row.cdmx.hour) == (2026, 4, 5, 0)


def test_april_day_is_24_hours_no_dst_jump(spark: SparkSession):
    """24 UTC hours across an April day convert to exactly 24 CDMX hours (no DST gap)."""
    t1 = int(datetime(2026, 4, 5, 0, 0, 0, tzinfo=UTC).timestamp())
    t2 = int(datetime(2026, 4, 6, 0, 0, 0, tzinfo=UTC).timestamp())
    rows = sorted(
        _ts_df(spark, t1, t2).withColumn("cdmx", to_cdmx_timestamp("ts")).collect(),
        key=lambda r: r.epoch_s,
    )
    delta = rows[1].cdmx - rows[0].cdmx
    assert delta.total_seconds() == 86400.0, (
        f"Expected 24h (86400s) gap in April, got {delta.total_seconds()}s"
    )


def test_epoch_ms_to_timestamp_divides_by_1000(spark: SparkSession):
    """Epoch milliseconds are divided by 1000 before cast: 1_700_000_000_000 ms = 1_700_000_000 s.

    TIMESTAMP_LTZ is collected in Python's local timezone, so we compare using
    datetime.fromtimestamp (local TZ) rather than utcfromtimestamp.
    """
    ms_schema = StructType([StructField("epoch_ms", LongType())])
    epoch_ms = 1_700_000_000_000
    df = spark.createDataFrame([(epoch_ms,)], ms_schema)
    row = df.withColumn("ts", epoch_ms_to_timestamp("epoch_ms")).collect()[0]
    expected = datetime.fromtimestamp(epoch_ms / 1000)
    assert row.ts == expected


def test_epoch_ms_to_timestamp_not_treated_as_seconds(spark: SparkSession):
    """Verify epoch_ms is NOT mis-treated as epoch seconds (which would give ~year 55000)."""
    ms_schema = StructType([StructField("epoch_ms", LongType())])
    epoch_ms = 1_700_000_000_000
    df = spark.createDataFrame([(epoch_ms,)], ms_schema)
    row = df.withColumn("ts", epoch_ms_to_timestamp("epoch_ms")).collect()[0]
    assert row.ts.year == 2023, f"Expected year 2023, got {row.ts.year} — likely missing /1000"


def test_extract_service_date_maps_utc_morning_to_prior_local_date(spark: SparkSession):
    """UTC 03:00 Jan 15 → service_date 2026-01-14 (CDMX wall-clock is Jan 14 21:00)."""
    epoch = int(datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC).timestamp())
    row = _ts_df(spark, epoch).withColumn("sd", extract_service_date("ts")).collect()[0]
    assert str(row.sd) == "2026-01-14"


def test_extract_service_date_afternoon_utc_stays_same_local_date(spark: SparkSession):
    """UTC 20:00 Jan 15 → service_date 2026-01-15 (CDMX wall-clock is Jan 15 14:00)."""
    epoch = int(datetime(2026, 1, 15, 20, 0, 0, tzinfo=UTC).timestamp())
    row = _ts_df(spark, epoch).withColumn("sd", extract_service_date("ts")).collect()[0]
    assert str(row.sd) == "2026-01-15"
