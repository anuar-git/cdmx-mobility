import datetime
import http.server
import json
import threading
import time

import httpx
import structlog
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2
from tenacity import retry, stop_after_attempt, wait_exponential

from ingestion.bq_logger import IngestionLogger, RunResult
from ingestion.config import Settings
from ingestion.gcs_uploader import GCSUploader

log = structlog.get_logger()


def _fetch_protobuf(url: str, timeout: int, max_retries: int) -> bytes:
    @retry(stop=stop_after_attempt(max_retries), wait=wait_exponential(min=2, max=10), reraise=True)
    def _inner() -> bytes:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return resp.content

    return _inner()


def _parse_to_ndjson(feed: gtfs_realtime_pb2.FeedMessage, snapshot_ts: str) -> bytes:
    """Return one JSON line per FeedEntity with _snapshot_ts injected."""
    lines = [
        json.dumps(
            {
                **MessageToDict(entity, preserving_proto_field_name=True),
                "_snapshot_ts": snapshot_ts,
            },
            ensure_ascii=False,
        )
        for entity in feed.entity
    ]
    return "\n".join(lines).encode()


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_: object) -> None:
        pass


def _start_health_server(port: int = 8080) -> None:
    """Bind a minimal HTTP health-check server on *port* in a daemon thread.

    Cloud Run Services require an HTTP endpoint to pass startup/liveness probes.
    This server is only reachable via internal GCP networking.
    """
    server = http.server.HTTPServer(("", port), _HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("health_server_started", port=port)


def run(settings: Settings) -> None:
    """Long-running daemon. Polls GTFS-RT vehicle positions every poll_interval_seconds.

    Each poll writes two objects to GCS:
      - Raw protobuf (.pb)  under metrobus/vehicle_positions_raw/
      - NDJSON conversion   under metrobus/vehicle_positions/  (for BigQuery external table)
    """
    _start_health_server()
    uploader = GCSUploader(bucket_name=settings.raw_bucket_name)
    bq_logger = IngestionLogger(project_id=settings.gcp_project_id)
    interval = settings.metrobus_gtfs_rt_poll_interval_seconds

    log.info(
        "gtfs_rt_daemon_starting",
        url=settings.metrobus_gtfs_rt_vehicle_positions_url,
        interval_s=interval,
    )

    while True:
        now = datetime.datetime.utcnow()
        today = now.strftime("%Y-%m-%d")
        snapshot_ts = now.strftime("%Y-%m-%dT%H:%M:%S")
        epoch_ms = int(now.timestamp() * 1000)
        result = RunResult(source="metrobus_gtfs_rt")

        try:
            raw = _fetch_protobuf(
                settings.metrobus_gtfs_rt_vehicle_positions_url,
                settings.http_timeout_seconds,
                settings.http_max_retries,
            )

            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(raw)
            entity_count = len(feed.entity)

            pb_path = f"metrobus/vehicle_positions_raw/ingestion_date={today}/vp_{epoch_ms}.pb"
            uploader.upload(raw, pb_path, content_type="application/octet-stream")

            ndjson = _parse_to_ndjson(feed, snapshot_ts)
            json_path = f"metrobus/vehicle_positions/ingestion_date={today}/vp_{epoch_ms}.ndjson"
            uploader.upload(ndjson, json_path, content_type="application/x-ndjson")

            result.file_count = 2
            result.byte_count = len(raw) + len(ndjson)
            result.row_count = entity_count

            log.info(
                "poll_ok",
                snapshot_ts=snapshot_ts,
                pb_bytes=len(raw),
                entities=entity_count,
            )

        except Exception as exc:
            result.status = "error"
            result.error_message = str(exc)
            log.exception("poll_failed", snapshot_ts=snapshot_ts)

        finally:
            bq_logger.log(result)

        time.sleep(interval)
