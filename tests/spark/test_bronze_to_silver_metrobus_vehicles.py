"""Unit tests for bronze_to_silver_metrobus_vehicles.py.

All tests use local Spark (fixture from conftest.py) and write fixtures to
pytest's tmp_path. No GCS access required.

Fixtures use a simplified GTFS-RT NDJSON format. Each line is a FeedEntity
JSON object with a nested `vehicle` struct, matching what MessageToDict()
produces from a GTFS-RT FeedMessage.

Coverage:
  _load_positions  — field extraction, H3 attachment, null-coordinate filter
  _load_stops      — latest-partition selection via path regex, H3 attachment
  _compute_dwell_events — session windowing, gap threshold, min-dwell filter,
                          service_date CDMX timezone, schema correctness
"""

import json
import os
from datetime import UTC, datetime

from pyspark.sql import SparkSession

from spark_jobs.bronze_to_silver_metrobus_vehicles import (
    MIN_DWELL_SECONDS,
    SESSION_GAP_SECONDS,
    _compute_dwell_events,
    _load_positions,
    _load_stops,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_TS = int(datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC).timestamp())  # noon UTC

_BASE_VEHICLE = {
    "vehicle": {"id": "V1", "label": "Bus 001"},
    "trip": {"route_id": "R1", "trip_id": "T1"},
    "position": {"latitude": 19.4326, "longitude": -99.1332},
    "current_status": "STOPPED_AT",
    "current_stop_sequence": 3,
    "timestamp": _BASE_TS,
}


def _write_ndjson(dirpath, filename: str, entities: list) -> None:
    """Write a list of FeedEntity-like dicts as NDJSON (one JSON per line)."""
    with open(os.path.join(dirpath, filename), "w") as f:
        for entity in entities:
            f.write(json.dumps(entity) + "\n")


def _entity(vehicle_id: str, route_id: str, lat: float, lon: float, ts: int, **overrides) -> dict:
    """Build a minimal FeedEntity dict for use in NDJSON fixtures."""
    v = {
        "vehicle": {"id": vehicle_id, "label": f"Bus {vehicle_id}"},
        "trip": {"route_id": route_id, "trip_id": f"T_{vehicle_id}"},
        "position": {"latitude": lat, "longitude": lon},
        "current_status": "STOPPED_AT",
        "current_stop_sequence": overrides.get("stop_sequence", 1),
        "timestamp": ts,
    }
    v.update({k: val for k, val in overrides.items() if k != "stop_sequence"})
    return {"id": f"e_{vehicle_id}_{ts}", "vehicle": v}


def _write_stops_csv(dirpath, filename: str, stops: list[dict]) -> None:
    """Write a minimal stops.csv with header."""
    header = "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station"
    rows = [header]
    for s in stops:
        rows.append(f"{s['stop_id']},{s['stop_name']},{s['stop_lat']},{s['stop_lon']},,")
    with open(os.path.join(dirpath, filename), "w") as f:
        f.write("\n".join(rows))


# ---------------------------------------------------------------------------
# _load_positions tests
# ---------------------------------------------------------------------------


def test_load_positions_extracts_fields(spark: SparkSession, tmp_path):
    """Field extraction from nested vehicle struct produces the expected columns."""
    _write_ndjson(tmp_path, "vp.ndjson", [{"id": "e1", "vehicle": _BASE_VEHICLE}])
    df = _load_positions(spark, str(tmp_path / "*.ndjson"))
    row = df.collect()[0]
    assert row.vehicle_id == "V1"
    assert row.route_id == "R1"
    assert row.trip_id == "T1"
    assert row.stop_sequence == 3
    assert abs(row.latitude - 19.4326) < 1e-4
    assert abs(row.longitude - (-99.1332)) < 1e-4
    assert row.position_h3 is not None


def test_load_positions_drops_null_coordinates(spark: SparkSession, tmp_path):
    """Rows with null latitude or longitude are dropped before H3 indexing."""
    bad = {
        "id": "e_bad",
        "vehicle": {
            **_BASE_VEHICLE,
            "position": {"latitude": None, "longitude": None},
        },
    }
    _write_ndjson(tmp_path, "vp.ndjson", [{"id": "e1", "vehicle": _BASE_VEHICLE}, bad])
    df = _load_positions(spark, str(tmp_path / "*.ndjson"))
    assert df.count() == 1


def test_load_positions_drops_null_vehicle(spark: SparkSession, tmp_path):
    """Entities without a vehicle field are filtered out."""
    _write_ndjson(
        tmp_path,
        "vp.ndjson",
        [
            {"id": "e1", "vehicle": _BASE_VEHICLE},
            {"id": "e2"},  # no vehicle key
        ],
    )
    df = _load_positions(spark, str(tmp_path / "*.ndjson"))
    assert df.count() == 1


def test_load_positions_output_schema(spark: SparkSession, tmp_path):
    """Output has all required columns for downstream snap and dwell steps."""
    _write_ndjson(tmp_path, "vp.ndjson", [{"id": "e1", "vehicle": _BASE_VEHICLE}])
    df = _load_positions(spark, str(tmp_path / "*.ndjson"))
    required = {
        "vehicle_id",
        "route_id",
        "trip_id",
        "latitude",
        "longitude",
        "timestamp",
        "position_h3",
    }
    assert required.issubset(set(df.columns))


# ---------------------------------------------------------------------------
# _load_stops tests
# ---------------------------------------------------------------------------

_STOP_A = {"stop_id": "S1", "stop_name": "Insurgentes", "stop_lat": 19.4273, "stop_lon": -99.1677}


def test_load_stops_picks_latest_partition(spark: SparkSession, tmp_path):
    """Only stops from the most recent ingestion_date partition are returned."""
    old_dir = tmp_path / "ingestion_date=2026-04-18"
    new_dir = tmp_path / "ingestion_date=2026-04-19"
    old_dir.mkdir()
    new_dir.mkdir()

    old_stop = {**_STOP_A, "stop_id": "OLD"}
    new_stop = {**_STOP_A, "stop_id": "NEW"}
    _write_stops_csv(old_dir, "stops.csv", [old_stop])
    _write_stops_csv(new_dir, "stops.csv", [new_stop])

    df = _load_stops(spark, str(tmp_path / "ingestion_date=*/stops.csv"))
    ids = {r.stop_id for r in df.collect()}
    assert "NEW" in ids
    assert "OLD" not in ids


def test_load_stops_attaches_h3(spark: SparkSession, tmp_path):
    """Each stop row gets a non-null stop_h3 cell index."""
    d = tmp_path / "ingestion_date=2026-04-20"
    d.mkdir()
    _write_stops_csv(d, "stops.csv", [_STOP_A])
    df = _load_stops(spark, str(tmp_path / "ingestion_date=*/stops.csv"))
    row = df.collect()[0]
    assert row.stop_h3 is not None


def test_load_stops_drops_null_stop_id(spark: SparkSession, tmp_path):
    """Rows with null stop_id are dropped."""
    d = tmp_path / "ingestion_date=2026-04-20"
    d.mkdir()
    _write_stops_csv(
        d,
        "stops.csv",
        [_STOP_A, {"stop_id": "", "stop_name": "Bad", "stop_lat": 0.0, "stop_lon": 0.0}],
    )
    df = _load_stops(spark, str(tmp_path / "ingestion_date=*/stops.csv"))
    # Empty string stop_id is null after CSV read with header
    assert all(r.stop_id is not None and r.stop_id != "" for r in df.collect())


# ---------------------------------------------------------------------------
# _compute_dwell_events tests
# ---------------------------------------------------------------------------


def _make_snapped_df(spark: SparkSession, rows: list[dict]) -> object:
    """Build a minimal snapped DataFrame for dwell event tests."""
    return spark.createDataFrame(rows)


def _snapped_row(
    vehicle_id: str,
    stop_id: str,
    ts_offset: int,
    route_id: str = "R1",
    trip_id: str = "T1",
) -> dict:
    """Build one row of the snapped positions DataFrame."""
    ts = datetime.fromtimestamp(_BASE_TS + ts_offset, tz=UTC).replace(tzinfo=None)
    return {
        "vehicle_id": vehicle_id,
        "stop_id": stop_id,
        "stop_name": f"Stop_{stop_id}",
        "route_id": route_id,
        "trip_id": trip_id,
        "stop_sequence": 1,
        "timestamp": ts,
    }


def test_dwell_single_observation_is_dropped(spark: SparkSession):
    """A single at-stop record has dwell_seconds=0, below MIN_DWELL_SECONDS; dropped."""
    rows = [_snapped_row("V1", "S1", 0)]
    df = _make_snapped_df(spark, rows)
    events = _compute_dwell_events(df)
    assert events.count() == 0


def test_dwell_contiguous_records_form_one_event(spark: SparkSession):
    """Consecutive records within SESSION_GAP_SECONDS collapse into one dwell event."""
    gap = SESSION_GAP_SECONDS // 2  # short gap → same session
    rows = [
        _snapped_row("V1", "S1", 0),
        _snapped_row("V1", "S1", gap),
        _snapped_row("V1", "S1", gap * 2),
    ]
    df = _make_snapped_df(spark, rows)
    events = _compute_dwell_events(df)
    assert events.count() == 1
    event = events.collect()[0]
    assert event.dwell_seconds >= gap * 2


def test_dwell_gap_breaks_session(spark: SparkSession):
    """A gap exceeding SESSION_GAP_SECONDS starts a new session."""
    rows = [
        _snapped_row("V1", "S1", 0),
        _snapped_row("V1", "S1", MIN_DWELL_SECONDS),  # closes first session
        # large gap → new session
        _snapped_row("V1", "S1", MIN_DWELL_SECONDS + SESSION_GAP_SECONDS + 60),
        _snapped_row("V1", "S1", MIN_DWELL_SECONDS + SESSION_GAP_SECONDS + 90),
    ]
    df = _make_snapped_df(spark, rows)
    events = _compute_dwell_events(df)
    assert events.count() == 2


def test_dwell_different_vehicles_independent(spark: SparkSession):
    """Session windows are per (vehicle_id, stop_id); two vehicles don't share sessions."""
    rows = [
        _snapped_row("V1", "S1", 0),
        _snapped_row("V1", "S1", MIN_DWELL_SECONDS),
        _snapped_row("V2", "S1", 0),
        _snapped_row("V2", "S1", MIN_DWELL_SECONDS),
    ]
    df = _make_snapped_df(spark, rows)
    events = _compute_dwell_events(df)
    vehicle_ids = {r.vehicle_id for r in events.collect()}
    assert vehicle_ids == {"V1", "V2"}


def test_dwell_output_schema(spark: SparkSession):
    """Output has all columns required for Silver partitioning and downstream marts."""
    rows = [
        _snapped_row("V1", "S1", 0),
        _snapped_row("V1", "S1", MIN_DWELL_SECONDS),
    ]
    df = _make_snapped_df(spark, rows)
    events = _compute_dwell_events(df)
    required = {
        "vehicle_id",
        "stop_id",
        "stop_name",
        "route_id",
        "trip_id",
        "stop_sequence",
        "dwell_start_ts",
        "dwell_end_ts",
        "dwell_seconds",
        "service_date",
    }
    assert required.issubset(set(events.columns))


def test_dwell_service_date_uses_cdmx_timezone(spark: SparkSession):
    """dwell_start_ts at UTC early morning maps to prior CDMX-local date.

    2026-01-15 03:00:00 UTC = 2026-01-14 21:00:00 CST (UTC-6).
    The service_date partition should be 2026-01-14.
    """
    ts_utc = datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC)
    # Use fromtimestamp (local TZ) so Spark stores the correct UTC epoch regardless
    # of the Python process timezone. replace(tzinfo=None) on a UTC-aware datetime
    # produces a naive datetime with UTC wall-clock values; Spark then re-adjusts it
    # by the Python local TZ, shifting the epoch.
    ts_naive = datetime.fromtimestamp(ts_utc.timestamp())
    ts2_naive = datetime.fromtimestamp(ts_utc.timestamp() + MIN_DWELL_SECONDS)

    rows = [
        {
            "vehicle_id": "V1",
            "stop_id": "S1",
            "stop_name": "X",
            "route_id": "R1",
            "trip_id": "T1",
            "stop_sequence": 1,
            "timestamp": ts_naive,
        },
        {
            "vehicle_id": "V1",
            "stop_id": "S1",
            "stop_name": "X",
            "route_id": "R1",
            "trip_id": "T1",
            "stop_sequence": 1,
            "timestamp": ts2_naive,
        },
    ]
    df = _make_snapped_df(spark, rows)
    events = _compute_dwell_events(df)
    row = events.collect()[0]
    assert str(row.service_date) == "2026-01-14"
