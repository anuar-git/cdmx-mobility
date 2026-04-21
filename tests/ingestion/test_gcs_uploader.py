from unittest.mock import MagicMock, patch

from ingestion.gcs_uploader import GCSUploader


def test_upload_returns_correct_gcs_uri():
    with patch("google.cloud.storage.Client") as mock_storage:
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.return_value.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_bucket.name = "cdmx-mobility-raw"

        uploader = GCSUploader(bucket_name="cdmx-mobility-raw")
        uri = uploader.upload(
            b"col1,col2\n1,2",
            "metro/affluence/ingestion_date=2025-03-01/f.csv",
        )

    assert uri == "gs://cdmx-mobility-raw/metro/affluence/ingestion_date=2025-03-01/f.csv"
    mock_blob.upload_from_string.assert_called_once_with(b"col1,col2\n1,2", content_type="text/csv")


def test_upload_uses_correct_gcs_path():
    with patch("google.cloud.storage.Client") as mock_storage:
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.return_value.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_bucket.name = "cdmx-mobility-raw"

        uploader = GCSUploader(bucket_name="cdmx-mobility-raw")
        uploader.upload(b"data", "metro/affluence/ingestion_date=2025-04-01/file.csv")

    mock_bucket.blob.assert_called_once_with("metro/affluence/ingestion_date=2025-04-01/file.csv")
