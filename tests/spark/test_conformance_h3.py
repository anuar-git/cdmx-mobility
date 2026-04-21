"""Tests for spark_jobs.conformance.h3_utils.

lat_lon_to_h3_udf — verified against a real CDMX coordinate (Insurgentes stop).
snap_to_nearest_stop — uses pre-computed H3 cells to avoid dependency on exact
  floating-point → cell assignments. Same cell = H3 distance 0, always matched.
  Different cell far away = no match (inner join drops it).
"""

import h3
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from pyspark.sql.types import DoubleType, StructField, StructType

from spark_jobs.conformance.h3_utils import (
    H3_RESOLUTION,
    lat_lon_to_h3_udf,
    snap_to_nearest_stop,
)

# Metrobús Line 1 Insurgentes stop (from stops.csv fixture used in other tests).
_STOP_LAT = 19.4273
_STOP_LON = -99.1677
_STOP_CELL = h3.geo_to_h3(_STOP_LAT, _STOP_LON, H3_RESOLUTION)

# Vehicle 30m north of the stop — well within one H3 resolution-9 hexagon (~174m edge).
_VEHICLE_LAT = _STOP_LAT + 0.0003  # ~33m northward
_VEHICLE_LON = _STOP_LON
_VEHICLE_CELL = h3.geo_to_h3(_VEHICLE_LAT, _VEHICLE_LON, H3_RESOLUTION)

# A far-away cell guaranteed to be at distance >> 2 from _STOP_CELL.
_FAR_CELL = h3.geo_to_h3(20.0, -100.0, H3_RESOLUTION)


# ---------------------------------------------------------------------------
# lat_lon_to_h3_udf tests
# ---------------------------------------------------------------------------


def test_lat_lon_to_h3_udf_returns_cell_for_cdmx_coords(spark: SparkSession):
    """lat_lon_to_h3_udf produces a non-null, correctly-formatted H3 cell string."""
    df = spark.createDataFrame([(_STOP_LAT, _STOP_LON)], ["lat", "lon"])
    row = df.withColumn("h3_cell", lat_lon_to_h3_udf(col("lat"), col("lon"))).collect()[0]
    assert row.h3_cell is not None
    # H3 resolution-9 cells are 15-character hex strings (1 mode + 1 res + 13 base-4).
    assert len(row.h3_cell) == 15
    assert row.h3_cell == _STOP_CELL


def test_lat_lon_to_h3_udf_null_lat_returns_null(spark: SparkSession):
    """Null latitude produces null output — no exception."""
    schema = StructType(
        [StructField("lat", DoubleType(), True), StructField("lon", DoubleType(), True)]
    )
    df = spark.createDataFrame([(None, _STOP_LON)], schema)
    row = df.withColumn("h3_cell", lat_lon_to_h3_udf(col("lat"), col("lon"))).collect()[0]
    assert row.h3_cell is None


def test_lat_lon_to_h3_udf_null_lon_returns_null(spark: SparkSession):
    """Null longitude produces null output."""
    schema = StructType(
        [StructField("lat", DoubleType(), True), StructField("lon", DoubleType(), True)]
    )
    df = spark.createDataFrame([(_STOP_LAT, None)], schema)
    row = df.withColumn("h3_cell", lat_lon_to_h3_udf(col("lat"), col("lon"))).collect()[0]
    assert row.h3_cell is None


def test_lat_lon_to_h3_udf_nearby_point_within_50m_same_or_adjacent_cell(spark: SparkSession):
    """A point 30m from a stop is in the same or an adjacent H3 cell (distance ≤ 1)."""
    dist = h3.h3_distance(_STOP_CELL, _VEHICLE_CELL)
    assert dist <= 1, f"Expected ≤1 H3 steps for 30m offset, got {dist}"


# ---------------------------------------------------------------------------
# snap_to_nearest_stop tests
# ---------------------------------------------------------------------------


def test_snap_matches_vehicle_in_same_cell_as_stop(spark: SparkSession):
    """A vehicle in the same H3 cell as a stop is snapped to that stop."""
    positions = spark.createDataFrame([(_STOP_CELL, "V1")], ["position_h3", "vehicle_id"])
    stops = spark.createDataFrame(
        [(_STOP_CELL, "S1", "Insurgentes")], ["stop_h3", "stop_id", "stop_name"]
    )
    result = snap_to_nearest_stop(positions, stops)
    assert result.count() == 1
    row = result.collect()[0]
    assert row.vehicle_id == "V1"
    assert row.stop_id == "S1"


def test_snap_drops_vehicle_in_different_cell(spark: SparkSession):
    """A vehicle whose H3 cell does not match any stop cell is dropped (inner join)."""
    positions = spark.createDataFrame([(_FAR_CELL, "V_far")], ["position_h3", "vehicle_id"])
    stops = spark.createDataFrame(
        [(_STOP_CELL, "S1", "Insurgentes")], ["stop_h3", "stop_id", "stop_name"]
    )
    result = snap_to_nearest_stop(positions, stops)
    assert result.count() == 0


def test_snap_multiple_vehicles_independent(spark: SparkSession):
    """Each vehicle is snapped independently; two vehicles at the same stop each get a row."""
    positions = spark.createDataFrame(
        [(_STOP_CELL, "V1"), (_STOP_CELL, "V2"), (_FAR_CELL, "V3")],
        ["position_h3", "vehicle_id"],
    )
    stops = spark.createDataFrame(
        [(_STOP_CELL, "S1", "Insurgentes")], ["stop_h3", "stop_id", "stop_name"]
    )
    result = snap_to_nearest_stop(positions, stops)
    snapped_ids = {r.vehicle_id for r in result.collect()}
    assert snapped_ids == {"V1", "V2"}
    assert "V3" not in snapped_ids
