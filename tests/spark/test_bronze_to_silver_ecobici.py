"""Unit tests for bronze_to_silver_ecobici.py.

All tests use local Spark (fixture from conftest.py) and write JSON fixtures to
pytest's tmp_path. No GCS access required.

Deduplication invariants verified:
  - First snapshot per station is always kept (no prev state to compare).
  - Identical consecutive snapshots are dropped.
  - A change in any of the four tracked fields triggers a new state-change row.
  - Compression ratio is at least 5x for realistic repetition patterns.

Service-date invariant:
  - UTC timestamps that fall before midnight in CDMX local time are mapped to
    the prior calendar date (UTC-6 offset in winter).
"""

import json
import os
from datetime import UTC, datetime

from pyspark.sql import SparkSession

from spark_jobs.bronze_to_silver_ecobici import (
    _transform_state_changes,
    _transform_station_master,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_STATION = {
    "station_id": "1",
    "num_bikes_available": 5,
    "num_docks_available": 10,
    "is_renting": 1,
    "is_returning": 1,
    "last_reported": 1_000_000,
}


def _snapshot(dirpath, ts_seconds: int, stations: list, filename: str) -> None:
    """Write a single GBFS station_status JSON envelope to dirpath."""
    payload = {"last_updated": ts_seconds, "ttl": 120, "data": {"stations": stations}}
    with open(os.path.join(dirpath, filename), "w") as f:
        json.dump(payload, f)


def _info_snapshot(dirpath, ts_seconds: int, stations: list, filename: str) -> None:
    """Write a single GBFS station_information JSON envelope to dirpath."""
    payload = {"last_updated": ts_seconds, "ttl": 86400, "data": {"stations": stations}}
    with open(os.path.join(dirpath, filename), "w") as f:
        json.dump(payload, f)


def _glob(tmp_path) -> str:
    return str(tmp_path / "*.json")


# ---------------------------------------------------------------------------
# State-change deduplication tests
# ---------------------------------------------------------------------------


def test_first_snapshot_per_station_always_kept(spark: SparkSession, tmp_path):
    """A station's very first snapshot is always a state-change row."""
    _snapshot(tmp_path, 1_000_000, [_BASE_STATION], "snap.json")
    df = _transform_state_changes(spark, _glob(tmp_path))
    assert df.count() == 1


def test_identical_consecutive_snapshot_dropped(spark: SparkSession, tmp_path):
    """Two consecutive identical snapshots → only the first is kept."""
    _snapshot(tmp_path, 1_000_000, [_BASE_STATION], "snap1.json")
    _snapshot(tmp_path, 1_000_120, [_BASE_STATION], "snap2.json")
    df = _transform_state_changes(spark, _glob(tmp_path))
    assert df.count() == 1


def test_bike_count_change_triggers_state_change(spark: SparkSession, tmp_path):
    """Dropping num_bikes_available by 1 produces a second state-change row."""
    _snapshot(tmp_path, 1_000_000, [_BASE_STATION], "snap1.json")
    changed = {**_BASE_STATION, "num_bikes_available": 4, "num_docks_available": 11}
    _snapshot(tmp_path, 1_000_120, [changed], "snap2.json")
    df = _transform_state_changes(spark, _glob(tmp_path))
    assert df.count() == 2


def test_is_renting_change_triggers_state_change(spark: SparkSession, tmp_path):
    """A station going out-of-service (is_renting → 0) triggers a state-change."""
    _snapshot(tmp_path, 1_000_000, [_BASE_STATION], "snap1.json")
    paused = {**_BASE_STATION, "is_renting": 0}
    _snapshot(tmp_path, 1_000_120, [paused], "snap2.json")
    df = _transform_state_changes(spark, _glob(tmp_path))
    assert df.count() == 2


def test_multiple_stations_deduped_independently(spark: SparkSession, tmp_path):
    """Each station's deduplication window is independent of other stations."""
    station_a = {**_BASE_STATION, "station_id": "A"}
    station_b = {**_BASE_STATION, "station_id": "B", "num_bikes_available": 3}

    _snapshot(tmp_path, 1_000_000, [station_a, station_b], "snap1.json")
    # B changes, A stays the same
    b_changed = {**station_b, "num_bikes_available": 2}
    _snapshot(tmp_path, 1_000_120, [station_a, b_changed], "snap2.json")

    df = _transform_state_changes(spark, _glob(tmp_path))
    all_rows = df.collect()

    # A(snap1) + B(snap1) + B(snap2) = 3 rows.
    # A(snap2) is dropped — A did not change between snapshots.
    assert len(all_rows) == 3

    a_rows = [r for r in all_rows if r.station_id == "A"]
    b_rows = sorted([r for r in all_rows if r.station_id == "B"], key=lambda r: r.snapshot_ts)

    assert len(a_rows) == 1
    assert a_rows[0].num_bikes_available == 5

    assert len(b_rows) == 2
    assert b_rows[0].num_bikes_available == 3  # initial
    assert b_rows[1].num_bikes_available == 2  # after change


def test_compression_ratio_at_least_5x(spark: SparkSession, tmp_path):
    """With 10 snapshots per 5 stations and only 2 changes per station, ratio >= 5."""
    n_stations = 5
    n_snapshots = 10

    for i in range(n_snapshots):
        ts = 1_000_000 + i * 120
        stations = []
        for sid in range(1, n_stations + 1):
            # First 5 snapshots: 10 bikes. Last 5: 8 bikes (one change per station).
            bikes = 10 if i < 5 else 8
            stations.append(
                {
                    "station_id": str(sid),
                    "num_bikes_available": bikes,
                    "num_docks_available": 20 - bikes,
                    "is_renting": 1,
                    "is_returning": 1,
                    "last_reported": ts,
                }
            )
        _snapshot(tmp_path, ts, stations, f"snap{i:02d}.json")

    df = _transform_state_changes(spark, _glob(tmp_path))
    input_count = n_stations * n_snapshots  # 50
    output_count = df.count()  # 5 x 2 changes = 10
    ratio = input_count / output_count
    assert ratio >= 5.0, f"Expected >= 5x compression, got {ratio:.2f}x"


def test_output_schema_has_required_columns(spark: SparkSession, tmp_path):
    """The output DataFrame has all columns needed for downstream Silver tables."""
    _snapshot(tmp_path, 1_000_000, [_BASE_STATION], "snap.json")
    df = _transform_state_changes(spark, _glob(tmp_path))
    expected = {
        "snapshot_ts",
        "station_id",
        "num_bikes_available",
        "num_docks_available",
        "is_renting",
        "is_returning",
        "last_reported",
        "service_date",
    }
    assert expected.issubset(set(df.columns))


# ---------------------------------------------------------------------------
# Service-date / timezone tests
# ---------------------------------------------------------------------------


def test_service_date_uses_cdmx_local_time(spark: SparkSession, tmp_path):
    """A UTC timestamp that falls before midnight in CDMX maps to the prior date.

    2026-01-15 03:00:00 UTC = 2026-01-14 21:00:00 CST (UTC-6 in January).
    The service_date should be 2026-01-14, not 2026-01-15.
    """
    ts = int(datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC).timestamp())
    _snapshot(tmp_path, ts, [_BASE_STATION], "snap.json")
    df = _transform_state_changes(spark, _glob(tmp_path))
    row = df.collect()[0]
    assert str(row.service_date) == "2026-01-14"


# ---------------------------------------------------------------------------
# Station master tests
# ---------------------------------------------------------------------------

_BASE_INFO_STATION = {
    "station_id": "1",
    "name": "Reforma",
    "lat": 19.4326,
    "lon": -99.1332,
    "capacity": 15,
}


def test_station_master_picks_latest_snapshot(spark: SparkSession, tmp_path):
    """station_master keeps only stations from the highest last_updated file."""
    old = [{**_BASE_INFO_STATION, "station_id": "OLD", "name": "Old Station"}]
    new = [{**_BASE_INFO_STATION, "station_id": "NEW", "name": "New Station"}]

    _info_snapshot(tmp_path, 1_000_000, old, "old.json")
    _info_snapshot(tmp_path, 2_000_000, new, "new.json")

    df = _transform_station_master(spark, _glob(tmp_path))
    rows = {r.station_id: r for r in df.collect()}

    assert "NEW" in rows, "Most recent station missing from master"
    assert "OLD" not in rows, "Stale station should not appear in master"
    assert rows["NEW"].name == "New Station"


def test_station_master_schema(spark: SparkSession, tmp_path):
    """station_master output has exactly the expected columns."""
    _info_snapshot(tmp_path, 1_000_000, [_BASE_INFO_STATION], "info.json")
    df = _transform_station_master(spark, _glob(tmp_path))
    assert set(df.columns) == {"station_id", "name", "lat", "lon", "capacity"}


def test_station_master_capacity_cast_to_int(spark: SparkSession, tmp_path):
    """capacity is cast to IntegerType, not left as string/double."""
    _info_snapshot(tmp_path, 1_000_000, [_BASE_INFO_STATION], "info.json")
    df = _transform_station_master(spark, _glob(tmp_path))
    capacity_type = dict(df.dtypes)["capacity"]
    assert capacity_type == "int", f"Expected int, got {capacity_type}"
