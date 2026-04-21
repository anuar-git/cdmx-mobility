import datetime
import io
import zipfile

import structlog

from ingestion.bq_logger import IngestionLogger, RunResult
from ingestion.ckan_client import CKANClient
from ingestion.config import Settings
from ingestion.gcs_uploader import GCSUploader
from ingestion.schema_validator import GTFS_STATIC_REQUIRED, validate_csv_header

log = structlog.get_logger()

# Standard GTFS files carried by the SEMOVI feed; others (agency.txt, feed_info.txt, …) skipped
_EXPECTED_FEEDS = {"stops", "routes", "trips", "stop_times", "calendar", "shapes"}


def _find_zip_resource(resources: list[dict]) -> dict:
    """Return the most-recently-modified ZIP resource from a CKAN resource list."""
    candidates = [
        r
        for r in resources
        if r.get("format", "").upper() in {"ZIP", "GTFS"}
        or r.get("url", "").lower().endswith(".zip")
    ]
    if not candidates:
        raise RuntimeError(f"No ZIP resource found among {len(resources)} CKAN resources")
    return max(candidates, key=lambda r: r.get("last_modified", ""))


def run(settings: Settings) -> None:
    bq_logger = IngestionLogger(project_id=settings.gcp_project_id)
    result = RunResult(source="metrobus_gtfs_static")

    try:
        client = CKANClient(
            base_url=settings.metro_ckan_base_url,
            timeout=settings.http_timeout_seconds,
            max_retries=settings.http_max_retries,
        )
        uploader = GCSUploader(bucket_name=settings.raw_bucket_name)
        today = datetime.date.today().isoformat()

        log.info("fetching_gtfs_resources", dataset=settings.metrobus_gtfs_static_dataset_id)
        resources = client.get_resources(settings.metrobus_gtfs_static_dataset_id)
        zip_resource = _find_zip_resource(resources)

        log.info("downloading_gtfs_zip", url=zip_resource["url"])
        zip_bytes = client.download_resource(zip_resource["url"])

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
