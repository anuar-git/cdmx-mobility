import io
import zipfile
from unittest.mock import patch

import pytest

from ingestion.config import Settings
from ingestion.metrobus.gtfs_static import _find_zip_resource, run

_ALL_EXPECTED_FEEDS = {"stops", "routes", "trips", "stop_times", "calendar", "shapes"}

# Per-feed CSV headers that satisfy schema validation (subset of required columns).
_FEED_HEADERS: dict[str, str] = {
    "stops": "stop_id,stop_name,stop_lat,stop_lon\n",
    "routes": "route_id,route_short_name,route_type\n",
    "trips": "route_id,service_id,trip_id\n",
    "stop_times": "trip_id,stop_id,stop_sequence\n",
    "calendar": "service_id,monday,start_date,end_date\n",
    "shapes": "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n",
}
_DATA_ROW = "val1,val2,val3,val4\n"

_ZIP_RESOURCE = {
    "name": "GTFS",
    "url": "https://datos.cdmx.gob.mx/gtfs.zip",
    "format": "ZIP",
    "last_modified": "2026-02-24",
}


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
        metro_ckan_base_url="https://ckan.example.com/api/3/action",
        metrobus_gtfs_static_dataset_id="gtfs",
        http_timeout_seconds=10,
        http_max_retries=1,
    )
    defaults.update(overrides)
    return Settings.model_construct(**defaults)


# --- _find_zip_resource ---


def test_find_zip_resource_by_format():
    resources = [
        {"name": "README", "url": "https://ex.com/readme.pdf", "format": "PDF"},
        _ZIP_RESOURCE,
    ]
    result = _find_zip_resource(resources)
    assert result["format"] == "ZIP"


def test_find_zip_resource_by_url_extension():
    resources = [{"name": "GTFS", "url": "https://ex.com/gtfs.zip", "format": ""}]
    result = _find_zip_resource(resources)
    assert result["url"].endswith(".zip")


def test_find_zip_resource_raises_if_none():
    resources = [{"name": "PDF", "url": "https://ex.com/info.pdf", "format": "PDF"}]
    with pytest.raises(RuntimeError, match="No ZIP resource found"):
        _find_zip_resource(resources)


def test_find_zip_resource_picks_most_recent():
    resources = [
        {**_ZIP_RESOURCE, "last_modified": "2024-01-01"},
        {**_ZIP_RESOURCE, "last_modified": "2026-02-24"},
        {**_ZIP_RESOURCE, "last_modified": "2025-06-15"},
    ]
    result = _find_zip_resource(resources)
    assert result["last_modified"] == "2026-02-24"


def test_find_zip_resource_accepts_gtfs_format():
    resources = [{"name": "Feed", "url": "https://ex.com/feed.zip", "format": "GTFS"}]
    result = _find_zip_resource(resources)
    assert result["name"] == "Feed"


# --- run() ---


def test_run_uploads_all_expected_feeds():
    zip_bytes = _make_gtfs_zip()
    with (
        patch("ingestion.metrobus.gtfs_static.CKANClient") as mock_client_class,
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
    ):
        mock_client_class.return_value.get_resources.return_value = [_ZIP_RESOURCE]
        mock_client_class.return_value.download_resource.return_value = zip_bytes
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"

        run(_settings())

    assert mock_uploader_class.return_value.upload.call_count == len(_ALL_EXPECTED_FEEDS)


def test_run_skips_unexpected_zip_entries():
    extra_feeds = _ALL_EXPECTED_FEEDS | {"agency", "feed_info", "frequencies"}
    zip_bytes = _make_gtfs_zip(extra_feeds)
    with (
        patch("ingestion.metrobus.gtfs_static.CKANClient") as mock_client_class,
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
    ):
        mock_client_class.return_value.get_resources.return_value = [_ZIP_RESOURCE]
        mock_client_class.return_value.download_resource.return_value = zip_bytes
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"

        run(_settings())

    assert mock_uploader_class.return_value.upload.call_count == len(_ALL_EXPECTED_FEEDS)


def test_run_uses_date_partition():
    zip_bytes = _make_gtfs_zip({"stops"})
    with (
        patch("ingestion.metrobus.gtfs_static.CKANClient") as mock_client_class,
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
    ):
        mock_client_class.return_value.get_resources.return_value = [_ZIP_RESOURCE]
        mock_client_class.return_value.download_resource.return_value = zip_bytes
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"

        run(_settings())

    gcs_path = mock_uploader_class.return_value.upload.call_args.args[1]
    assert "ingestion_date=" in gcs_path
    assert gcs_path.startswith("metrobus/static/stops/")
    assert gcs_path.endswith("stops.csv")


def test_run_uses_text_csv_content_type():
    zip_bytes = _make_gtfs_zip({"routes"})
    with (
        patch("ingestion.metrobus.gtfs_static.CKANClient") as mock_client_class,
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
    ):
        mock_client_class.return_value.get_resources.return_value = [_ZIP_RESOURCE]
        mock_client_class.return_value.download_resource.return_value = zip_bytes
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"

        run(_settings())

    upload_call = mock_uploader_class.return_value.upload.call_args
    assert upload_call.kwargs["content_type"] == "text/csv"


def test_run_raises_if_no_zip_resource():
    with (
        patch("ingestion.metrobus.gtfs_static.CKANClient") as mock_client_class,
        patch("ingestion.metrobus.gtfs_static.GCSUploader"),
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
    ):
        mock_client_class.return_value.get_resources.return_value = [
            {"name": "SHP", "url": "https://ex.com/shapes.shp", "format": "SHP"}
        ]

        with pytest.raises(RuntimeError, match="No ZIP resource found"):
            run(_settings())


def test_run_passes_correct_ckan_dataset_id():
    zip_bytes = _make_gtfs_zip({"stops"})
    with (
        patch("ingestion.metrobus.gtfs_static.CKANClient") as mock_client_class,
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
    ):
        mock_client_class.return_value.get_resources.return_value = [_ZIP_RESOURCE]
        mock_client_class.return_value.download_resource.return_value = zip_bytes
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"

        run(_settings(metrobus_gtfs_static_dataset_id="gtfs"))

    mock_client_class.return_value.get_resources.assert_called_once_with("gtfs")


def test_run_raises_on_invalid_csv_header():
    # A zip where stops.txt has wrong headers should fail validation
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("stops.txt", b"wrong_col1,wrong_col2\nval1,val2\n")
    bad_zip = buf.getvalue()

    with (
        patch("ingestion.metrobus.gtfs_static.CKANClient") as mock_client_class,
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger"),
    ):
        mock_client_class.return_value.get_resources.return_value = [_ZIP_RESOURCE]
        mock_client_class.return_value.download_resource.return_value = bad_zip

        with pytest.raises(ValueError, match="stop_id"):
            run(_settings())

    mock_uploader_class.return_value.upload.assert_not_called()


def test_run_logs_metrics_to_bq():
    zip_bytes = _make_gtfs_zip(_ALL_EXPECTED_FEEDS)
    with (
        patch("ingestion.metrobus.gtfs_static.CKANClient") as mock_client_class,
        patch("ingestion.metrobus.gtfs_static.GCSUploader") as mock_uploader_class,
        patch("ingestion.metrobus.gtfs_static.IngestionLogger") as mock_logger_class,
    ):
        mock_client_class.return_value.get_resources.return_value = [_ZIP_RESOURCE]
        mock_client_class.return_value.download_resource.return_value = zip_bytes
        mock_uploader_class.return_value.upload.return_value = "gs://test-bucket/path"

        run(_settings())

    mock_logger_class.return_value.log.assert_called_once()
    result_arg = mock_logger_class.return_value.log.call_args[0][0]
    assert result_arg.source == "metrobus_gtfs_static"
    assert result_arg.status == "success"
    assert result_arg.file_count == len(_ALL_EXPECTED_FEEDS)
    assert result_arg.byte_count > 0
