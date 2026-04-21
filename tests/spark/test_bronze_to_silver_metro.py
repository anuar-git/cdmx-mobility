"""Tests for spark_jobs.bronze_to_silver_metro_affluence._transform.

The metro affluence CSVs have one row per (fecha, linea, estacion) with a
daily total — no wide-to-long reshape. Tests cover column output, station name
canonicalization, double-encoded UTF-8 mojibake fix, and null filtering.

Mojibake fixture note: "á" in UTF-8 is 0xC3 0xA1. If the file was originally
encoded as Latin-1 and then mistakenly re-encoded as UTF-8, those two bytes
appear as the Unicode pair (Ã, ¡) = U+00C3 U+00A1. Writing those characters to
a UTF-8 fixture file and reading with Spark reproduces the production scenario.
"""

import os

from pyspark.sql import SparkSession

from spark_jobs.bronze_to_silver_metro_affluence import _transform

_HEADER = "fecha,anio,mes,linea,estacion,afluencia"


def _write_csv(tmp_path, rows: list[str], filename: str = "affluence.csv") -> str:
    content = "\n".join([_HEADER, *rows]) + "\n"
    path = os.path.join(tmp_path, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(tmp_path / "*.csv")


# ---------------------------------------------------------------------------
# Schema and column tests
# ---------------------------------------------------------------------------


def test_transform_output_columns(spark: SparkSession, tmp_path):
    """Output contains service_date, linea, station_raw, station_canonical, daily_entries."""
    glob = _write_csv(tmp_path, ["2026-01-15,2026,1,L1,Pantitlan,50000"])
    df = _transform(spark, glob)
    expected = {"service_date", "linea", "station_raw", "station_canonical", "daily_entries"}
    assert expected.issubset(set(df.columns))
    # anio, mes, fecha, afluencia (raw) must not appear
    for dropped in ("fecha", "anio", "mes", "afluencia"):
        assert dropped not in df.columns, f"Column {dropped!r} should have been dropped"


def test_transform_daily_entries_is_integer(spark: SparkSession, tmp_path):
    """daily_entries is cast to IntegerType, not left as string."""
    glob = _write_csv(tmp_path, ["2026-01-15,2026,1,L1,Pantitlan,50000"])
    df = _transform(spark, glob)
    assert dict(df.dtypes)["daily_entries"] == "int"


# ---------------------------------------------------------------------------
# Station name canonicalization
# ---------------------------------------------------------------------------


def test_transform_canonicalizes_known_variant(spark: SparkSession, tmp_path):
    """'GARIBALDI' (pre-rename variant) is canonicalized to 'Garibaldi/Lagunilla'."""
    glob = _write_csv(tmp_path, ["2026-01-15,2026,1,L1,GARIBALDI,30000"])
    df = _transform(spark, glob)
    row = df.collect()[0]
    assert row.station_raw == "GARIBALDI"
    assert row.station_canonical == "Garibaldi/Lagunilla"


def test_transform_preserves_raw_station_name(spark: SparkSession, tmp_path):
    """station_raw keeps the original value for auditability."""
    glob = _write_csv(tmp_path, ["2026-01-15,2026,1,L1,GARIBALDI,30000"])
    df = _transform(spark, glob)
    row = df.collect()[0]
    assert row.station_raw == "GARIBALDI"


def test_transform_passthrough_for_unknown_station(spark: SparkSession, tmp_path):
    """An unrecognised station name is returned unchanged in both raw and canonical."""
    glob = _write_csv(tmp_path, ["2026-01-15,2026,1,L1,Estacion Nueva,20000"])
    df = _transform(spark, glob)
    row = df.collect()[0]
    assert row.station_raw == "Estacion Nueva"
    assert row.station_canonical == "Estacion Nueva"


# ---------------------------------------------------------------------------
# Null filtering
# ---------------------------------------------------------------------------


def test_transform_drops_row_with_invalid_date(spark: SparkSession, tmp_path):
    """Rows where fecha cannot be parsed to DATE are dropped."""
    glob = _write_csv(
        tmp_path,
        [
            "2026-01-15,2026,1,L1,Pantitlan,50000",  # valid
            "not-a-date,2026,1,L1,Pantitlan,10000",  # invalid → dropped
        ],
    )
    df = _transform(spark, glob)
    assert df.count() == 1


def test_transform_drops_row_with_null_affluence(spark: SparkSession, tmp_path):
    """Rows with empty or non-numeric afluencia are dropped after cast to int."""
    glob = _write_csv(
        tmp_path,
        [
            "2026-01-15,2026,1,L1,Pantitlan,50000",  # valid
            "2026-01-15,2026,1,L1,Zocalo,",  # empty → null → dropped
            "2026-01-15,2026,1,L1,Zocalo,-",  # dash → null → dropped
        ],
    )
    df = _transform(spark, glob)
    assert df.count() == 1


# ---------------------------------------------------------------------------
# Double-encoded UTF-8 (mojibake) fix
# ---------------------------------------------------------------------------


def test_transform_fixes_mojibake_station_name(spark: SparkSession, tmp_path):
    """Double-encoded UTF-8 in station names is reversed by the encoding fix UDF.

    'PantitlÃ¡n' (Ã = U+00C3, ¡ = U+00A1) is the mojibake for 'Pantitlán'.
    When written to a UTF-8 file and read by Spark, the fix_encoding UDF
    re-encodes the characters as Latin-1 (recovering the original UTF-8 bytes)
    then decodes as UTF-8 to produce the correct accented name.
    """
    # Mojibake: á (U+00E1, UTF-8 0xC3 0xA1) → misread as Latin-1 → (Ã U+00C3, ¡ U+00A1)
    mojibake_name = "PantitlÃ\u00a1n"  # "PantitlÃ¡n"
    glob = _write_csv(tmp_path, [f"2026-01-15,2026,1,L1,{mojibake_name},50000"])
    df = _transform(spark, glob)
    row = df.collect()[0]
    # After encoding fix: "Pantitlán" — already canonical, passthrough in station lookup
    assert "á" in row.station_raw, f"Expected fixed encoding, got {row.station_raw!r}"
