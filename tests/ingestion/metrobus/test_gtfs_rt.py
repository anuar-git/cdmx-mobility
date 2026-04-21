import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from google.transit import gtfs_realtime_pb2

from ingestion.config import Settings
from ingestion.metrobus.gtfs_rt import _fetch_protobuf, _parse_to_ndjson, run


def _make_feed(num_entities: int = 2) -> gtfs_realtime_pb2.FeedMessage:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1700000000
    for i in range(num_entities):
        entity = feed.entity.add()
        entity.id = f"vehicle-{i}"
        vp = entity.vehicle
        vp.vehicle.id = f"v{i}"
        vp.vehicle.label = f"MB-{i:03d}"
        vp.trip.route_id = f"route-{i + 1}"
        vp.position.latitude = 19.4 + i * 0.001
        vp.position.longitude = -99.1 - i * 0.001
        vp.position.bearing = float(i * 45)
        vp.position.speed = 5.0 + i
        vp.current_status = gtfs_realtime_pb2.VehiclePosition.IN_TRANSIT_TO
    return feed


def _make_feed_bytes(num_entities: int = 2) -> bytes:
    return _make_feed(num_entities).SerializeToString()


def _settings(**overrides) -> Settings:
    defaults = dict(
        gcp_project_id="test-project",
        raw_bucket_name="test-bucket",
        metrobus_gtfs_rt_vehicle_positions_url="https://rt.example.com/vp.pb",
        metrobus_gtfs_rt_poll_interval_seconds=30,
        http_timeout_seconds=10,
        http_max_retries=1,
    )
    defaults.update(overrides)
    return Settings.model_construct(**defaults)


# --- _parse_to_ndjson ---


def test_parse_to_ndjson_one_line_per_entity():
    feed = _make_feed(3)
    result = _parse_to_ndjson(feed, "2024-01-01T12:00:00")
    lines = result.decode().strip().split("\n")
    assert len(lines) == 3


def test_parse_to_ndjson_adds_snapshot_ts():
    feed = _make_feed(1)
    result = _parse_to_ndjson(feed, "2024-01-01T12:00:00")
    record = json.loads(result.decode().strip())
    assert record["_snapshot_ts"] == "2024-01-01T12:00:00"


def test_parse_to_ndjson_empty_feed():
    feed = _make_feed(0)
    result = _parse_to_ndjson(feed, "2024-01-01T12:00:00")
    assert result == b""


def test_parse_to_ndjson_includes_entity_id_and_vehicle():
    feed = _make_feed(1)
    result = _parse_to_ndjson(feed, "2024-01-01T12:00:00")
    record = json.loads(result.decode().strip())
    assert record["id"] == "vehicle-0"
    assert "vehicle" in record


def test_parse_to_ndjson_uses_snake_case_field_names():
    feed = _make_feed(1)
    result = _parse_to_ndjson(feed, "2024-01-01T12:00:00")
    record = json.loads(result.decode().strip())
    vehicle = record["vehicle"]
    assert "current_status" in vehicle or "trip" in vehicle


# --- _fetch_protobuf ---


def test_fetch_protobuf_retries_and_reraises():
    call_count = [0]

    def _always_fail(*_args, **_kwargs):
        call_count[0] += 1
        raise httpx.NetworkError("connection refused")

    with patch("time.sleep"), patch("httpx.Client") as mock_client_class:  # suppress tenacity wait
        mock_client_class.return_value.__enter__.return_value.get.side_effect = _always_fail
        with pytest.raises(httpx.NetworkError):
            _fetch_protobuf("https://rt.example.com/vp.pb", timeout=10, max_retries=3)

    assert call_count[0] == 3


def test_fetch_protobuf_succeeds_on_second_attempt():
    call_count = [0]
    good_response = MagicMock()
    good_response.content = b"pb_data"
    good_response.raise_for_status = MagicMock()

    def _fail_then_succeed(*_args, **_kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise httpx.NetworkError("temporary")
        return good_response

    with patch("time.sleep"), patch("httpx.Client") as mock_client_class:
        mock_client_class.return_value.__enter__.return_value.get.side_effect = _fail_then_succeed
        result = _fetch_protobuf("https://rt.example.com/vp.pb", timeout=10, max_retries=3)

    assert result == b"pb_data"
    assert call_count[0] == 2


# --- run() ---


def test_run_uploads_pb_and_ndjson(monkeypatch):
    def _stop(_n: int) -> None:
        raise StopIteration

    monkeypatch.setattr("time.sleep", _stop)
    raw_bytes = _make_feed_bytes(2)

    with (
        patch("ingestion.metrobus.gtfs_rt._fetch_protobuf", return_value=raw_bytes),
        patch("ingestion.metrobus.gtfs_rt._start_health_server"),
        patch("ingestion.metrobus.gtfs_rt.IngestionLogger"),
        patch("ingestion.metrobus.gtfs_rt.GCSUploader") as mock_uploader_class,
    ):
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"
        with pytest.raises(StopIteration):
            run(_settings())

    upload_calls = mock_uploader_class.return_value.upload.call_args_list
    assert len(upload_calls) == 2
    paths = [c.args[1] for c in upload_calls]
    assert any("vehicle_positions_raw" in p for p in paths)
    assert any("vehicle_positions/" in p and p.endswith(".ndjson") for p in paths)


def test_run_uses_date_partition(monkeypatch):
    def _stop(_n: int) -> None:
        raise StopIteration

    monkeypatch.setattr("time.sleep", _stop)
    raw_bytes = _make_feed_bytes(1)

    with (
        patch("ingestion.metrobus.gtfs_rt._fetch_protobuf", return_value=raw_bytes),
        patch("ingestion.metrobus.gtfs_rt._start_health_server"),
        patch("ingestion.metrobus.gtfs_rt.IngestionLogger"),
        patch("ingestion.metrobus.gtfs_rt.GCSUploader") as mock_uploader_class,
    ):
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"
        with pytest.raises(StopIteration):
            run(_settings())

    for call in mock_uploader_class.return_value.upload.call_args_list:
        assert "ingestion_date=" in call.args[1]


def test_run_continues_after_http_error(monkeypatch):
    poll_count = [0]

    def _stop_after_two(_n: int) -> None:
        if poll_count[0] >= 2:
            raise StopIteration

    monkeypatch.setattr("time.sleep", _stop_after_two)
    raw_bytes = _make_feed_bytes(1)

    def _mock_fetch(url: str, timeout: int, max_retries: int) -> bytes:
        poll_count[0] += 1
        if poll_count[0] == 1:
            raise RuntimeError("network error")
        return raw_bytes

    with (
        patch("ingestion.metrobus.gtfs_rt._fetch_protobuf", side_effect=_mock_fetch),
        patch("ingestion.metrobus.gtfs_rt._start_health_server"),
        patch("ingestion.metrobus.gtfs_rt.IngestionLogger"),
        patch("ingestion.metrobus.gtfs_rt.GCSUploader") as mock_uploader_class,
    ):
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"
        with pytest.raises(StopIteration):
            run(_settings())

    # Poll 1 failed (0 uploads), poll 2 succeeded (pb + ndjson = 2 uploads)
    assert mock_uploader_class.return_value.upload.call_count == 2


def test_run_logs_success_to_bq(monkeypatch):
    def _stop(_n: int) -> None:
        raise StopIteration

    monkeypatch.setattr("time.sleep", _stop)
    raw_bytes = _make_feed_bytes(2)

    with (
        patch("ingestion.metrobus.gtfs_rt._fetch_protobuf", return_value=raw_bytes),
        patch("ingestion.metrobus.gtfs_rt._start_health_server"),
        patch("ingestion.metrobus.gtfs_rt.IngestionLogger") as mock_logger_class,
        patch("ingestion.metrobus.gtfs_rt.GCSUploader") as mock_uploader_class,
    ):
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"
        with pytest.raises(StopIteration):
            run(_settings())

    mock_logger_class.return_value.log.assert_called_once()
    result_arg = mock_logger_class.return_value.log.call_args[0][0]
    assert result_arg.source == "metrobus_gtfs_rt"
    assert result_arg.status == "success"
    assert result_arg.file_count == 2
    assert result_arg.row_count == 2


def test_run_logs_error_to_bq(monkeypatch):
    poll_count = [0]

    def _stop_after_one(_n: int) -> None:
        if poll_count[0] >= 1:
            raise StopIteration

    monkeypatch.setattr("time.sleep", _stop_after_one)

    def _mock_fetch(url: str, timeout: int, max_retries: int) -> bytes:
        poll_count[0] += 1
        raise RuntimeError("endpoint down")

    with (
        patch("ingestion.metrobus.gtfs_rt._fetch_protobuf", side_effect=_mock_fetch),
        patch("ingestion.metrobus.gtfs_rt._start_health_server"),
        patch("ingestion.metrobus.gtfs_rt.IngestionLogger") as mock_logger_class,
        patch("ingestion.metrobus.gtfs_rt.GCSUploader"),
        pytest.raises(StopIteration),
    ):
        run(_settings())

    result_arg = mock_logger_class.return_value.log.call_args[0][0]
    assert result_arg.status == "error"
    assert "endpoint down" in result_arg.error_message


def test_run_calls_start_health_server(monkeypatch):
    def _stop(_n: int) -> None:
        raise StopIteration

    monkeypatch.setattr("time.sleep", _stop)
    raw_bytes = _make_feed_bytes(1)

    with (
        patch("ingestion.metrobus.gtfs_rt._fetch_protobuf", return_value=raw_bytes),
        patch("ingestion.metrobus.gtfs_rt._start_health_server") as mock_health,
        patch("ingestion.metrobus.gtfs_rt.IngestionLogger"),
        patch("ingestion.metrobus.gtfs_rt.GCSUploader") as mock_uploader_class,
    ):
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"
        with pytest.raises(StopIteration):
            run(_settings())

    mock_health.assert_called_once()


def test_run_pb_uses_octet_stream_content_type(monkeypatch):
    def _stop(_n: int) -> None:
        raise StopIteration

    monkeypatch.setattr("time.sleep", _stop)
    raw_bytes = _make_feed_bytes(1)

    with (
        patch("ingestion.metrobus.gtfs_rt._fetch_protobuf", return_value=raw_bytes),
        patch("ingestion.metrobus.gtfs_rt._start_health_server"),
        patch("ingestion.metrobus.gtfs_rt.IngestionLogger"),
        patch("ingestion.metrobus.gtfs_rt.GCSUploader") as mock_uploader_class,
    ):
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"
        with pytest.raises(StopIteration):
            run(_settings())

    upload_calls = mock_uploader_class.return_value.upload.call_args_list
    pb_call = next(c for c in upload_calls if "vehicle_positions_raw" in c.args[1])
    assert pb_call.kwargs["content_type"] == "application/octet-stream"
