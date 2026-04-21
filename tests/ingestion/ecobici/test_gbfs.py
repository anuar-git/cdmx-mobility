from unittest.mock import patch

import pytest

from ingestion.config import Settings
from ingestion.ecobici.gbfs import run

MOCK_FEED = {"last_updated": 1700000000, "ttl": 120, "data": {"stations": []}}
MOCK_FEED_WITH_STATIONS = {
    "last_updated": 1700000000,
    "ttl": 120,
    "data": {"stations": [{"station_id": "1"}, {"station_id": "2"}]},
}


def _settings(**overrides) -> Settings:
    defaults = dict(
        gcp_project_id="test-project",
        raw_bucket_name="test-bucket",
        ecobici_gbfs_base_url="https://gbfs.example.com/gbfs/es",
        ecobici_api_key="",
        ecobici_poll_feeds=["station_information", "station_status", "system_alerts"],
        http_timeout_seconds=10,
        http_max_retries=1,
    )
    defaults.update(overrides)
    return Settings.model_construct(**defaults)


def test_run_uploads_all_feeds():
    with (
        patch("ingestion.ecobici.gbfs.GBFSClient") as mock_client_class,
        patch("ingestion.ecobici.gbfs.GCSUploader") as mock_uploader_class,
        patch("ingestion.ecobici.gbfs.IngestionLogger"),
    ):
        mock_client_class.return_value.fetch.return_value = MOCK_FEED
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/ecobici/..."

        run(_settings())

    assert mock_client_class.return_value.fetch.call_count == 3
    assert mock_uploader_class.return_value.upload.call_count == 3
    for upload_call in mock_uploader_class.return_value.upload.call_args_list:
        assert upload_call.kwargs["content_type"] == "application/json"


def test_run_station_information_uses_date_partition():
    with (
        patch("ingestion.ecobici.gbfs.GBFSClient") as mock_client_class,
        patch("ingestion.ecobici.gbfs.GCSUploader") as mock_uploader_class,
        patch("ingestion.ecobici.gbfs.IngestionLogger"),
    ):
        mock_client_class.return_value.fetch.return_value = MOCK_FEED
        run(_settings(ecobici_poll_feeds=["station_information"]))

    gcs_path = mock_uploader_class.return_value.upload.call_args.args[1]
    assert "ingestion_date=" in gcs_path
    assert "ingestion_ts=" not in gcs_path
    assert gcs_path.startswith("ecobici/station_information/")


def test_run_station_status_uses_ts_partition():
    with (
        patch("ingestion.ecobici.gbfs.GBFSClient") as mock_client_class,
        patch("ingestion.ecobici.gbfs.GCSUploader") as mock_uploader_class,
        patch("ingestion.ecobici.gbfs.IngestionLogger"),
    ):
        mock_client_class.return_value.fetch.return_value = MOCK_FEED
        run(_settings(ecobici_poll_feeds=["station_status"]))

    gcs_path = mock_uploader_class.return_value.upload.call_args.args[1]
    assert "ingestion_ts=" in gcs_path
    assert "ingestion_date=" not in gcs_path
    assert gcs_path.startswith("ecobici/station_status/")


def test_run_system_alerts_uses_ts_partition():
    with (
        patch("ingestion.ecobici.gbfs.GBFSClient") as mock_client_class,
        patch("ingestion.ecobici.gbfs.GCSUploader") as mock_uploader_class,
        patch("ingestion.ecobici.gbfs.IngestionLogger"),
    ):
        mock_client_class.return_value.fetch.return_value = MOCK_FEED
        run(_settings(ecobici_poll_feeds=["system_alerts"]))

    gcs_path = mock_uploader_class.return_value.upload.call_args.args[1]
    assert "ingestion_ts=" in gcs_path
    assert gcs_path.startswith("ecobici/system_alerts/")


def test_run_passes_api_key_to_client():
    with (
        patch("ingestion.ecobici.gbfs.GBFSClient") as mock_client_class,
        patch("ingestion.ecobici.gbfs.GCSUploader"),
        patch("ingestion.ecobici.gbfs.IngestionLogger"),
    ):
        mock_client_class.return_value.fetch.return_value = MOCK_FEED
        run(_settings(ecobici_api_key="my-key", ecobici_poll_feeds=["station_status"]))

    _, kwargs = mock_client_class.call_args
    assert kwargs["api_key"] == "my-key"


def test_run_raises_on_invalid_gbfs_envelope():
    bad_feed = {"last_updated": 1700000000}  # missing ttl and data

    with (
        patch("ingestion.ecobici.gbfs.GBFSClient") as mock_client_class,
        patch("ingestion.ecobici.gbfs.GCSUploader") as mock_uploader_class,
        patch("ingestion.ecobici.gbfs.IngestionLogger"),
    ):
        mock_client_class.return_value.fetch.return_value = bad_feed
        with pytest.raises(ValueError, match="missing keys"):
            run(_settings(ecobici_poll_feeds=["station_status"]))

    mock_uploader_class.return_value.upload.assert_not_called()


def test_run_logs_success_with_station_count():
    with (
        patch("ingestion.ecobici.gbfs.GBFSClient") as mock_client_class,
        patch("ingestion.ecobici.gbfs.GCSUploader") as mock_uploader_class,
        patch("ingestion.ecobici.gbfs.IngestionLogger") as mock_logger_class,
    ):
        mock_client_class.return_value.fetch.return_value = MOCK_FEED_WITH_STATIONS
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/ecobici/..."
        run(_settings(ecobici_poll_feeds=["station_status"]))

    result_arg = mock_logger_class.return_value.log.call_args[0][0]
    assert result_arg.status == "success"
    assert result_arg.row_count == 2
    assert result_arg.file_count == 1


def test_run_logs_error_on_fetch_failure():
    with (
        patch("ingestion.ecobici.gbfs.GBFSClient") as mock_client_class,
        patch("ingestion.ecobici.gbfs.GCSUploader"),
        patch("ingestion.ecobici.gbfs.IngestionLogger") as mock_logger_class,
    ):
        mock_client_class.return_value.fetch.side_effect = RuntimeError("timeout")
        with pytest.raises(RuntimeError):
            run(_settings(ecobici_poll_feeds=["station_status"]))

    result_arg = mock_logger_class.return_value.log.call_args[0][0]
    assert result_arg.status == "error"
    assert "timeout" in result_arg.error_message
