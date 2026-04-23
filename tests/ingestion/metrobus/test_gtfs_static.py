import io
import zipfile
from unittest.mock import patch

import pytest

from ingestion.config import Settings
from ingestion.metrobus.gtfs_static import run

_ALL_EXPECTED_FEEDS = {"stops", "routes", "trips", "stop_times", "calendar", "shapes"}

_FEED_HEADERS: dict[str, str] = {
    "stops": "stop_id,stop_name,stop_lat,stop_lon\n",
    "routes": "route_id,route_short_name,route_type\n",
    "trips": "route_id,service_id,trip_id\n",
    "stop_times": "trip_id,stop_id,stop_sequence\n",
    "calendar": "service_id,monday,start_date,end_date\n",
    "shapes": "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n",
}
_DATA_ROW = "val1,val2,val3,val4\n"


def _make_gtfs_zip(feeds: set[str] | None = None) -> bytes:
    if feeds is None:
        feeds = _ALL_EXPECTED_FEEDS
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(feeds):
            content = _FEED_HEADERS.get(name, "col1,col2\n") + _DATA_ROW
            zf.writestr(f"{name}.txt", content.encode())
    return buf.getvalue()


def _settings(**overrides) -> Settings:
    defaults = dict(
        gcp_project_id="test-project",
        raw_bucket_name="test-bucket",
        http_timeout_seconds=10,
        http_max_retries=1,
    )
    defaults.update(overrides)
    return Settings.model_construct(**defaults)


# --- run() ---


def test_run_uploads_all_expected_feeds():
    zip_bytes = _make_gtfs_zip()
    with (
        patch(
            "ingestion.metrobus.gtfs_static._latest_static_zip",
            return_value=(
                "metrobus/gtfs_static_email/ingestion_date=2026-04-23/gtfs.zip",
                zip_bytes,
            ),
        ),
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
    ):
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"
        run(_settings())

    assert mock_uploader_class.return_value.upload.call_count == len(_ALL_EXPECTED_FEEDS)


def test_run_skips_unexpected_zip_entries():
    extra_feeds = _ALL_EXPECTED_FEEDS | {"agency", "feed_info", "frequencies"}
    zip_bytes = _make_gtfs_zip(extra_feeds)
    with (
        patch(
            "ingestion.metrobus.gtfs_static._latest_static_zip",
            return_value=(
                "metrobus/gtfs_static_email/ingestion_date=2026-04-23/gtfs.zip",
                zip_bytes,
            ),
        ),
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
    ):
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"
        run(_settings())

    assert mock_uploader_class.return_value.upload.call_count == len(_ALL_EXPECTED_FEEDS)


def test_run_uses_date_partition():
    zip_bytes = _make_gtfs_zip({"stops"})
    with (
        patch(
            "ingestion.metrobus.gtfs_static._latest_static_zip",
            return_value=(
                "metrobus/gtfs_static_email/ingestion_date=2026-04-23/gtfs.zip",
                zip_bytes,
            ),
        ),
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
    ):
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"
        run(_settings())

    gcs_path = mock_uploader_class.return_value.upload.call_args.args[1]
    assert "ingestion_date=" in gcs_path
    assert gcs_path.startswith("metrobus/static/stops/")
    assert gcs_path.endswith("stops.csv")


def test_run_uses_text_csv_content_type():
    zip_bytes = _make_gtfs_zip({"routes"})
    with (
        patch(
            "ingestion.metrobus.gtfs_static._latest_static_zip",
            return_value=(
                "metrobus/gtfs_static_email/ingestion_date=2026-04-23/gtfs.zip",
                zip_bytes,
            ),
        ),
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
    ):
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"
        run(_settings())

    upload_call = mock_uploader_class.return_value.upload.call_args
    assert upload_call.kwargs["content_type"] == "text/csv"


def test_run_raises_if_no_static_zip_in_gcs():
    with (
        patch(
            "ingestion.metrobus.gtfs_static._latest_static_zip",
            side_effect=RuntimeError("No static GTFS ZIP found in GCS"),
        ),
        patch("ingestion.metrobus.gtfs_static.GCSUploader"),
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
        pytest.raises(RuntimeError, match="No static GTFS ZIP found in GCS"),
    ):
        run(_settings())


def test_run_raises_on_invalid_csv_header():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("stops.txt", b"wrong_col1,wrong_col2\nval1,val2\n")
    bad_zip = buf.getvalue()

    with (
        patch(
            "ingestion.metrobus.gtfs_static._latest_static_zip",
            return_value=(
                "metrobus/gtfs_static_email/ingestion_date=2026-04-23/gtfs.zip",
                bad_zip,
            ),
        ),
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
        pytest.raises(ValueError, match="stop_id"),
    ):
        run(_settings())

    mock_uploader_class.return_value.upload.assert_not_called()


def test_run_logs_metrics_to_bq():
    zip_bytes = _make_gtfs_zip(_ALL_EXPECTED_FEEDS)
    with (
        patch(
            "ingestion.metrobus.gtfs_static._latest_static_zip",
            return_value=(
                "metrobus/gtfs_static_email/ingestion_date=2026-04-23/gtfs.zip",
                zip_bytes,
            ),
        ),
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger") as mock_logger_class,
    ):
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"
        run(_settings())

    mock_logger_class.return_value.log.assert_called_once()
    result_arg = mock_logger_class.return_value.log.call_args[0][0]
    assert result_arg.source == "metrobus_gtfs_static"
    assert result_arg.status == "success"
    assert result_arg.file_count == len(_ALL_EXPECTED_FEEDS)
    assert result_arg.byte_count > 0
