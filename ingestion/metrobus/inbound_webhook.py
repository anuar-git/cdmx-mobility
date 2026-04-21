"""SendGrid Inbound Parse webhook handler.

sinopticoplus sends an HTML email containing download links to .proto binary
files (not MIME attachments). This handler:
  1. Receives the raw MIME email from SendGrid.
  2. Extracts href links pointing to .proto files from the HTML body.
  3. Downloads each file with httpx.
  4. RT file  → parse as GTFS-RT FeedMessage → NDJSON + raw .pb to GCS.
  5. Static file → archive raw bytes to GCS.
  6. Logs RunResult to meta_cdmx.ingestion_log.
"""

import datetime
import email as stdlib_email
import json
import re
from html.parser import HTMLParser
from urllib.parse import unquote

import httpx
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2

from ingestion.bq_logger import IngestionLogger, RunResult
from ingestion.config import Settings
from ingestion.gcs_uploader import GCSUploader

log = structlog.get_logger()
app = FastAPI()

_settings: Settings | None = None
_uploader: GCSUploader | None = None
_bq_logger: IngestionLogger | None = None


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for attr, val in attrs:
                if attr == "href" and val:
                    self.links.append(val)


@app.on_event("startup")
def _startup() -> None:
    global _settings, _uploader, _bq_logger
    _settings = Settings()
    _uploader = GCSUploader(bucket_name=_settings.raw_bucket_name)
    _bq_logger = IngestionLogger(project_id=_settings.gcp_project_id)
    log.info("inbound_webhook_ready", bucket=_settings.raw_bucket_name)


@app.get("/healthz")
def health() -> str:
    return "ok"


@app.post("/inbound/{secret}")
async def handle_inbound(secret: str, request: Request) -> JSONResponse:
    if secret != _settings.metrobus_inbound_webhook_secret:
        raise HTTPException(status_code=403, detail="forbidden")

    form = await request.form()
    raw_mime: str | None = form.get("email")
    if not raw_mime:
        log.warning("missing_raw_mime", keys=list(form.keys()))
        return JSONResponse({"status": "ok", "skipped": "no raw mime"})

    msg = stdlib_email.message_from_string(raw_mime)
    html_body = next(
        (
            part.get_payload(decode=True).decode(errors="replace")
            for part in msg.walk()
            if part.get_content_type() == "text/html" and part.get_payload(decode=True)
        ),
        "",
    )

    extractor = _LinkExtractor()
    extractor.feed(html_body)
    proto_urls = [url for url in extractor.links if ".proto" in url.lower()]
    log.info("proto_links_found", count=len(proto_urls), urls=proto_urls)

    if not proto_urls:
        log.warning("no_proto_links_in_email")
        return JSONResponse({"status": "ok", "skipped": "no proto links"})

    now = datetime.datetime.utcnow()
    today = now.strftime("%Y-%m-%d")
    snapshot_ts = now.strftime("%Y-%m-%dT%H:%M:%S")
    epoch_ms = int(now.timestamp() * 1000)
    result = RunResult(source="metrobus_gtfs_inbound")

    try:
        total_bytes = 0
        file_count = 0
        entity_count = 0

        with httpx.Client(timeout=_settings.http_timeout_seconds, follow_redirects=True) as client:
            for url in proto_urls:
                match = re.search(r"/([^/?]+\.proto)", unquote(url), re.IGNORECASE)
                fname = match.group(1) if match else url.split("/")[-1].split("?")[0]
                resp = client.get(url)
                resp.raise_for_status()
                raw_bytes = resp.content
                log.info("proto_downloaded", filename=fname, bytes=len(raw_bytes))

                if "RT" in fname.upper():
                    feed = gtfs_realtime_pb2.FeedMessage()
                    feed.ParseFromString(raw_bytes)
                    entity_count = len(feed.entity)

                    pb_path = (
                        f"metrobus/vehicle_positions_raw/ingestion_date={today}/vp_{epoch_ms}.pb"
                    )
                    _uploader.upload(raw_bytes, pb_path, content_type="application/octet-stream")

                    ndjson = _parse_to_ndjson(feed, snapshot_ts)
                    ndjson_path = (
                        f"metrobus/vehicle_positions/ingestion_date={today}/vp_{epoch_ms}.ndjson"
                    )
                    _uploader.upload(ndjson, ndjson_path, content_type="application/x-ndjson")

                    total_bytes += len(raw_bytes) + len(ndjson)
                    file_count += 2
                    log.info("rt_parsed", entities=entity_count, snapshot_ts=snapshot_ts)
                else:
                    static_path = f"metrobus/gtfs_static_email/ingestion_date={today}/{fname}"
                    _uploader.upload(
                        raw_bytes, static_path, content_type="application/octet-stream"
                    )
                    total_bytes += len(raw_bytes)
                    file_count += 1
                    log.info("static_archived", filename=fname, bytes=len(raw_bytes))

        result.file_count = file_count
        result.byte_count = total_bytes
        result.row_count = entity_count
        return JSONResponse({"status": "ok", "entities": entity_count})

    except Exception as exc:
        result.status = "error"
        result.error_message = str(exc)
        log.exception("inbound_webhook_failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    finally:
        _bq_logger.log(result)


def _parse_to_ndjson(feed: gtfs_realtime_pb2.FeedMessage, snapshot_ts: str) -> bytes:
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


def serve(port: int = 8080) -> None:
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
