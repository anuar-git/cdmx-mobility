import datetime

import httpx
import structlog

from ingestion.bq_logger import IngestionLogger, RunResult
from ingestion.ckan_client import CKANClient
from ingestion.config import Settings
from ingestion.gcs_uploader import GCSUploader
from ingestion.schema_validator import METRO_AFFLUENCE_REQUIRED, validate_csv_header

log = structlog.get_logger()


def run(settings: Settings) -> None:
    bq_logger = IngestionLogger(project_id=settings.gcp_project_id)
    result = RunResult(source="metro_affluence")

    try:
        client = CKANClient(
            base_url=settings.metro_ckan_base_url,
            timeout=settings.http_timeout_seconds,
            max_retries=settings.http_max_retries,
        )
        uploader = GCSUploader(bucket_name=settings.raw_bucket_name)
        today = datetime.date.today().isoformat()

        resources = client.get_resources(settings.metro_affluence_dataset_id)
        csv_resources = [
            r
            for r in resources
            if r.get("format", "").upper() == "CSV"
            and "diccionario" not in r.get("name", "").lower()
        ]

        log.info("resources_found", total=len(resources), csv=len(csv_resources))

        for resource in csv_resources:
            filename = resource["url"].split("/")[-1]
            subfolder = (
                "metro/affluence_desglosado"
                if "desglosado" in filename.lower()
                else "metro/affluence_simple"
            )
            gcs_path = f"{subfolder}/ingestion_date={today}/{filename}"
            log.info("downloading", resource_name=resource["name"], url=resource["url"])
            data = client.download_resource(resource["url"])

            validate_csv_header(
                data, METRO_AFFLUENCE_REQUIRED, source=f"metro_affluence/{filename}"
            )

            destination = uploader.upload(data, gcs_path)
            log.info("uploaded", destination=destination, bytes=len(data))

            result.file_count += 1
            result.byte_count += len(data)
            result.row_count = (result.row_count or 0) + max(0, len(data.splitlines()) - 1)

    except (httpx.ConnectTimeout, httpx.ConnectError) as exc:
        # datos.cdmx.gob.mx is intermittently unreachable (server-side downtime).
        # The dataset updates monthly; skipping one daily run loses no data.
        # Log the skip to BQ and exit cleanly so CI does not fail.
        result.status = "skipped"
        result.error_message = str(exc)
        log.warning("ckan_unreachable_skipping", error=str(exc))

    except Exception as exc:
        result.status = "error"
        result.error_message = str(exc)
        raise

    finally:
        bq_logger.log(result)
