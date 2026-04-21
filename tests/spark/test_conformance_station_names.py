"""Tests for spark_jobs.conformance.station_names.

One parametrized test per entry in METRO_STATION_CANONICAL verifies every
known variant spelling maps to the correct canonical name. Additional tests
cover None input, passthrough for unknown names, and case-insensitivity.
"""

import pytest
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from pyspark.sql.types import StringType, StructField, StructType

from spark_jobs.conformance.station_names import (
    METRO_STATION_CANONICAL,
    canonicalize_station_udf,
)


@pytest.mark.parametrize("variant,canonical", list(METRO_STATION_CANONICAL.items()))
def test_canonical_variant_maps_correctly(spark: SparkSession, variant: str, canonical: str):
    """Every key in METRO_STATION_CANONICAL resolves to the expected canonical name.

    The UDF normalises input with .strip().upper() before the dict lookup, so
    the dict keys are already in normalised form. Passing the key directly and
    its lowercase version both exercise the lookup path.
    """
    df = spark.createDataFrame([(variant,), (variant.lower(),)], ["name"])
    rows = df.withColumn("canon", canonicalize_station_udf(col("name"))).collect()
    for row in rows:
        assert row.canon == canonical, (
            f"variant={variant!r} → expected {canonical!r}, got {row.canon!r}"
        )


def test_none_input_returns_none(spark: SparkSession):
    """Null station name passes through as null — no KeyError."""
    schema = StructType([StructField("name", StringType(), True)])
    df = spark.createDataFrame([(None,)], schema)
    row = df.withColumn("canon", canonicalize_station_udf(col("name"))).collect()[0]
    assert row.canon is None


def test_unknown_station_passes_through_unchanged(spark: SparkSession):
    """A station name not in the lookup table is returned unchanged."""
    unknown = "Estación Desconocida"
    df = spark.createDataFrame([(unknown,)], ["name"])
    row = df.withColumn("canon", canonicalize_station_udf(col("name"))).collect()[0]
    assert row.canon == unknown


def test_leading_trailing_whitespace_stripped(spark: SparkSession):
    """Names with surrounding whitespace are normalised before lookup."""
    df = spark.createDataFrame([("  GARIBALDI  ",)], ["name"])
    row = df.withColumn("canon", canonicalize_station_udf(col("name"))).collect()[0]
    assert row.canon == "Garibaldi/Lagunilla"


def test_already_canonical_name_passes_through(spark: SparkSession):
    """A correctly spelled canonical name that is not a dict key returns itself."""
    # "Tacubaya" is in the dict as a sentinel: TACUBAYA → Tacubaya (identity).
    # "Copilco" is not in the dict at all — should return as-is.
    df = spark.createDataFrame([("Copilco",)], ["name"])
    row = df.withColumn("canon", canonicalize_station_udf(col("name"))).collect()[0]
    assert row.canon == "Copilco"
