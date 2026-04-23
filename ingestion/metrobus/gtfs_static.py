import datetime
import io
import zipfile

import structlog
from google.cloud import storage

from ingestion.bq_logger import IngestionLogger, RunResult
from ingestion.config import Settings
from ingestion.gcs_uploader import GCSUploader
from ingestion.schema_validator import GTFS_STATIC_REQUIRED, validate_csv_header

log = structlog.get_logger()

_EXPECTED_FEEDS = {"stops", "routes", "trips", "stop_times", "calendar", "shapes"}


def _latest_static_zip(bucket_name: str) -> tuple[str, bytes]:
    """Return (blob_name, bytes) for the most recent static GTFS ZIP archived by the webhook."""
    client = storage.Client()
    blobs = list(client.list_blobs(bucket_name, prefix="metrobus/gtfs_static_email/"))
    if not blobs:
        raise RuntimeError("No static GTFS ZIP found in GCS — webhook may not have run yet")
    latest = max(blobs, key=lambda b: b.updated)
    log.info("using_static_zip", blob=latest.name, updated=latest.updated.isoformat())
    return latest.name, latest.download_as_bytes()


def run(settings: Settings) -> None:
    bq_logger = IngestionLogger(project_id=settings.gcp_project_id)
    result = RunResult(source="metrobus_gtfs_static")

    try:
        uploader = GCSUploader(bucket_name=settings.raw_bucket_name)
        today = datetime.date.today().isoformat()

        _, zip_bytes = _latest_static_zip(settings.raw_bucket_name)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for entry in zf.namelist():
                feed_name = entry.removesuffix(".txt")
                if feed_name not in _EXPECTED_FEEDS:
                    log.debug("skipping_feed", entry=entry)
                    continue

                data = zf.read(entry)

                if feed_name in GTFS_STATIC_REQUIRED:
                    validate_csv_header(
                        data, GTFS_STATIC_REQUIRED[feed_name], source=f"gtfs_static/{feed_name}"
                    )

                gcs_path = f"metrobus/static/{feed_name}/ingestion_date={today}/{feed_name}.csv"
                dest = uploader.upload(data, gcs_path, content_type="text/csv")
                log.info("uploaded", feed=feed_name, dest=dest, bytes=len(data))

                result.file_count += 1
                result.byte_count += len(data)
                result.row_count = (result.row_count or 0) + max(0, len(data.splitlines()) - 1)

    except Exception as exc:
        result.status = "error"
        result.error_message = str(exc)
        raise

    finally:
        bq_logger.log(result)
