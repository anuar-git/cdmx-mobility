"""H3 spatial indexing utilities for Metrobús stop snapping.

Uses h3==3.7.7 (H3 Python bindings v3). The v3 API uses different function names
than v4: geo_to_h3() (not latlng_to_cell) and h3_distance() (not grid_distance).

Resolution 9 hexagons have an average edge length of ~174m. Two cells at
resolution 9 span at most ~350m — a safe upper bound for matching a vehicle
GPS position to its assigned stop when the vehicle is within 50m of that stop.
"""

from __future__ import annotations

import h3
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, explode, lit, monotonically_increasing_id, row_number, udf
from pyspark.sql.types import ArrayType, IntegerType, StringType
from pyspark.sql.window import Window

H3_RESOLUTION: int = 9  # ~174m average edge length


def _lat_lon_to_h3(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return None
    return h3.geo_to_h3(lat, lon, H3_RESOLUTION)


def _h3_distance(cell_a: str | None, cell_b: str | None) -> int | None:
    if cell_a is None or cell_b is None:
        return None
    try:
        return h3.h3_distance(cell_a, cell_b)
    except Exception:
        # h3.H3ResFailed or h3.H3Error when cells are at different resolutions
        # or too far apart for the distance algorithm to succeed.
        return None


def _h3_kring(cell: str | None, k: int) -> list[str] | None:
    if cell is None:
        return None
    return list(h3.k_ring(cell, k))


lat_lon_to_h3_udf = udf(_lat_lon_to_h3, StringType())
h3_distance_udf = udf(_h3_distance, IntegerType())
h3_kring_udf = udf(_h3_kring, ArrayType(StringType()))


def register_udfs(spark: SparkSession) -> None:
    """Register H3 UDFs for SQL-style use.

    Call once at job startup. Python DataFrame API callers can use
    lat_lon_to_h3_udf and h3_distance_udf directly without calling this.
    """
    spark.udf.register("lat_lon_to_h3", _lat_lon_to_h3, StringType())
    spark.udf.register("h3_distance", _h3_distance, IntegerType())


def snap_to_nearest_stop(
    positions_df: DataFrame,
    stops_df: DataFrame,
    position_h3_col: str = "position_h3",
    stop_h3_col: str = "stop_h3",
    max_h3_distance: int = 2,
) -> DataFrame:
    """Join each position row to its nearest stop within max_h3_distance grid steps.

    This is a DataFrame function rather than a UDF because it operates across
    two DataFrames simultaneously. A UDF processes a single row; joining two
    tables requires a distributed join operation that only the DataFrame API
    can express.

    Algorithm:
      1. Assign a stable internal ID to each position row so the window function
         can partition correctly even when position rows have no natural unique key.
      2. Join positions to stops on exact H3 cell match. This limits the join
         to ~7 candidate stops per position (one cell + 6 neighbors at distance 1,
         or ~19 at distance 2) rather than a full cross-join over all stops.
      3. Compute the precise H3 grid distance between each position cell and each
         candidate stop cell, then filter to max_h3_distance.
      4. Rank candidates by distance and keep rank=1 (nearest stop per position).
      5. Drop the internal position ID before returning.

    Both DataFrames must already have their H3 columns computed via
    lat_lon_to_h3_udf before calling this function.

    Args:
        positions_df: Must contain position_h3_col.
        stops_df: Must contain stop_h3_col. Column names must not overlap with
            positions_df except for the H3 join key.
        position_h3_col: Name of the H3 index column in positions_df.
        stop_h3_col: Name of the H3 index column in stops_df.
        max_h3_distance: Maximum grid distance to consider a stop reachable.
            Distance 2 covers ~350m at resolution 9.

    Returns:
        positions_df with all stops_df columns appended, one row per position.
        Positions with no stop within max_h3_distance are dropped (inner join).
    """
    pos_id_col = "_snap_pos_id"

    positions_with_id = positions_df.withColumn(pos_id_col, monotonically_increasing_id())

    # Expand each position cell to its k_ring neighborhood, then explode so
    # every candidate cell becomes a separate row for the join.
    # This fixes the original exact-cell join which silently dropped all stops
    # in neighbouring cells (the _h3_dist filter never ran on those rows).
    positions_expanded = (
        positions_with_id.withColumn(
            "_candidate_cells", h3_kring_udf(col(position_h3_col), lit(max_h3_distance))
        )
        .withColumn("_candidate_cell", explode("_candidate_cells"))
        .drop("_candidate_cells")
    )

    joined = positions_expanded.join(
        stops_df,
        on=positions_expanded["_candidate_cell"] == stops_df[stop_h3_col],
        how="inner",
    )

    joined = joined.withColumn(
        "_h3_dist",
        h3_distance_udf(col(position_h3_col), col(stop_h3_col)),
    ).filter((col("_h3_dist").isNotNull()) & (col("_h3_dist") <= max_h3_distance))

    w = Window.partitionBy(pos_id_col).orderBy(col("_h3_dist").asc())
    result = (
        joined.withColumn("_rank", row_number().over(w))
        .filter(col("_rank") == 1)
        .drop(pos_id_col, "_h3_dist", "_rank", "_candidate_cell")
    )

    return result
