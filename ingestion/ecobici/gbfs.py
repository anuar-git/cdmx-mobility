import datetime
import json

import structlog

from ingestion.bq_logger import IngestionLogger, RunResult
from ingestion.config import Settings
from ingestion.gbfs_client import GBFSClient
from ingestion.gcs_uploader import GCSUploader
from ingestion.schema_validator import validate_gbfs_envelope

log = structlog.get_logger()

# station_information is relatively static; partition by date rather than minute
_STATIC_FEEDS = {"station_information"}


def run(settings: Settings) -> None:
    bq_logger = IngestionLogger(project_id=settings.gcp_project_id)

    for feed_name in settings.ecobici_poll_feeds:
        result = RunResult(source=f"ecobici_{feed_name}")

        try:
            client = GBFSClient(
                base_url=settings.ecobici_gbfs_base_url,
                timeout=settings.http_timeout_seconds,
                max_retries=settings.http_max_retries,
                api_key=settings.ecobici_api_key,
            )
            uploader = GCSUploader(bucket_name=settings.raw_bucket_name)
            now = datetime.datetime.utcnow()
            ingestion_ts = now.strftime("%Y-%m-%dT%H-%M")
            today = now.strftime("%Y-%m-%d")

            log.info("fetching_feed", feed=feed_name)
            payload = client.fetch(feed_name)

            validate_gbfs_envelope(payload, feed_name)

            data = json.dumps(payload).encode()

            if feed_name in _STATIC_FEEDS:
                gcs_path = f"ecobici/{feed_name}/ingestion_date={today}/{feed_name}.json"
            else:
                gcs_path = f"ecobici/{feed_name}/ingestion_ts={ingestion_ts}/{feed_name}.json"

            destination = uploader.upload(data, gcs_path, content_type="application/json")
            log.info("uploaded", feed=feed_name, destination=destination, bytes=len(data))

            result.file_count = 1
            result.byte_count = len(data)
            stations = payload.get("data", {}).get("stations")
            if stations is not None:
                result.row_count = len(stations)

        except Exception as exc:
            result.status = "error"
            result.error_message = str(exc)
            raise

        finally:
            bq_logger.log(result)
