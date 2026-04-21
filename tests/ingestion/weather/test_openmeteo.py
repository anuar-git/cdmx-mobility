import json
from unittest.mock import patch

import pytest

from ingestion.config import Settings
from ingestion.weather.openmeteo import COORDINATES, _validate, run

_HOURS = [f"2026-04-19T{h:02d}:00" for h in range(24)]

_MOCK_PAYLOAD = {
    "latitude": 19.4326,
    "longitude": -99.1332,
    "hourly": {
        "time": _HOURS,
        "temperature_2m": [20.0] * 24,
        "precipitation": [0.0] * 24,
        "windspeed_10m": [2.0] * 24,
        "relativehumidity_2m": [60.0] * 24,
    },
}


def _settings(**overrides) -> Settings:
    defaults = dict(
        gcp_project_id="test-project",
        raw_bucket_name="test-bucket",
        weather_openmeteo_base_url="https://api.open-meteo.com/v1/forecast",
        http_timeout_seconds=10,
        http_max_retries=1,
    )
    defaults.update(overrides)
    return Settings.model_construct(**defaults)


# ---------------------------------------------------------------------------
# _validate tests
# ---------------------------------------------------------------------------


def test_validate_passes_on_complete_payload():
    _validate(_MOCK_PAYLOAD, "centro")  # must not raise


def test_validate_raises_on_missing_time():
    bad = {"hourly": {"temperature_2m": [1.0]}}
    with pytest.raises(ValueError, match=r"hourly\.time"):
        _validate(bad, "centro")


def test_validate_raises_on_missing_variable():
    bad = {"hourly": {"time": _HOURS}}  # missing temperature_2m etc.
    with pytest.raises(ValueError, match="temperature_2m"):
        _validate(bad, "centro")


def test_validate_raises_on_empty_time():
    bad = {
        "hourly": {
            "time": [],
            "temperature_2m": [],
            "precipitation": [],
            "windspeed_10m": [],
            "relativehumidity_2m": [],
        }
    }
    with pytest.raises(ValueError, match=r"hourly\.time"):
        _validate(bad, "centro")


# ---------------------------------------------------------------------------
# run() tests
# ---------------------------------------------------------------------------


def test_run_fetches_all_coordinates():
    with (
        patch("ingestion.weather.openmeteo.OpenMeteoClient") as mock_client_cls,
        patch("ingestion.weather.openmeteo.GCSUploader"),
        patch("ingestion.weather.openmeteo.IngestionLogger"),
    ):
        mock_client_cls.return_value.fetch.return_value = _MOCK_PAYLOAD
        run(_settings())

    assert mock_client_cls.return_value.fetch.call_count == len(COORDINATES)


def test_run_uploads_single_ndjson_file():
    with (
        patch("ingestion.weather.openmeteo.OpenMeteoClient") as mock_client_cls,
        patch("ingestion.weather.openmeteo.GCSUploader") as mock_uploader_cls,
        patch("ingestion.weather.openmeteo.IngestionLogger"),
    ):
        mock_client_cls.return_value.fetch.return_value = _MOCK_PAYLOAD
        mock_uploader_cls.return_value.upload.return_value = "gs://test-bucket/..."
        run(_settings())

    assert mock_uploader_cls.return_value.upload.call_count == 1


def test_run_upload_path_contains_ingestion_date():
    with (
        patch("ingestion.weather.openmeteo.OpenMeteoClient") as mock_client_cls,
        patch("ingestion.weather.openmeteo.GCSUploader") as mock_uploader_cls,
        patch("ingestion.weather.openmeteo.IngestionLogger"),
    ):
        mock_client_cls.return_value.fetch.return_value = _MOCK_PAYLOAD
        mock_uploader_cls.return_value.upload.return_value = "gs://test-bucket/..."
        run(_settings())

    gcs_path = mock_uploader_cls.return_value.upload.call_args.args[1]
    assert "ingestion_date=" in gcs_path
    assert gcs_path.startswith("weather/hourly/")


def test_run_ndjson_has_five_lines():
    with (
        patch("ingestion.weather.openmeteo.OpenMeteoClient") as mock_client_cls,
        patch("ingestion.weather.openmeteo.GCSUploader") as mock_uploader_cls,
        patch("ingestion.weather.openmeteo.IngestionLogger"),
    ):
        mock_client_cls.return_value.fetch.return_value = _MOCK_PAYLOAD
        mock_uploader_cls.return_value.upload.return_value = "gs://test-bucket/..."
        run(_settings())

    uploaded_bytes = mock_uploader_cls.return_value.upload.call_args.args[0]
    lines = uploaded_bytes.decode("utf-8").strip().split("\n")
    assert len(lines) == len(COORDINATES)


def test_run_each_ndjson_line_is_valid_json_with_coordinate_id():
    with (
        patch("ingestion.weather.openmeteo.OpenMeteoClient") as mock_client_cls,
        patch("ingestion.weather.openmeteo.GCSUploader") as mock_uploader_cls,
        patch("ingestion.weather.openmeteo.IngestionLogger"),
    ):
        mock_client_cls.return_value.fetch.return_value = _MOCK_PAYLOAD
        mock_uploader_cls.return_value.upload.return_value = "gs://test-bucket/..."
        run(_settings())

    uploaded_bytes = mock_uploader_cls.return_value.upload.call_args.args[0]
    lines = uploaded_bytes.decode("utf-8").strip().split("\n")
    coord_ids = [json.loads(line)["coordinate_id"] for line in lines]
    expected_ids = [c["id"] for c in COORDINATES]
    assert coord_ids == expected_ids


def test_run_logs_success_with_row_count():
    with (
        patch("ingestion.weather.openmeteo.OpenMeteoClient") as mock_client_cls,
        patch("ingestion.weather.openmeteo.GCSUploader") as mock_uploader_cls,
        patch("ingestion.weather.openmeteo.IngestionLogger") as mock_logger_cls,
    ):
        mock_client_cls.return_value.fetch.return_value = _MOCK_PAYLOAD
        mock_uploader_cls.return_value.upload.return_value = "gs://test-bucket/..."
        run(_settings())

    result = mock_logger_cls.return_value.log.call_args[0][0]
    assert result.status == "success"
    assert result.file_count == 1
    # 5 coordinates x 24 hours each = 120 total hourly observations
    assert result.row_count == len(COORDINATES) * 24


def test_run_logs_error_on_fetch_failure():
    with (
        patch("ingestion.weather.openmeteo.OpenMeteoClient") as mock_client_cls,
        patch("ingestion.weather.openmeteo.GCSUploader"),
        patch("ingestion.weather.openmeteo.IngestionLogger") as mock_logger_cls,
    ):
        mock_client_cls.return_value.fetch.side_effect = RuntimeError("API down")
        with pytest.raises(RuntimeError):
            run(_settings())

    result = mock_logger_cls.return_value.log.call_args[0][0]
    assert result.status == "error"
    assert "API down" in result.error_message
