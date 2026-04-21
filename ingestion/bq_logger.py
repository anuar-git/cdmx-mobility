import datetime
import uuid
from dataclasses import dataclass, field

import structlog
from google.cloud import bigquery

log = structlog.get_logger()

_TABLE_ID = "meta_cdmx.ingestion_log"


@dataclass
class RunResult:
    source: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_count: int = 0
    byte_count: int = 0
    row_count: int | None = None
    status: str = "success"
    error_message: str | None = None
    ingested_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)


class IngestionLogger:
    def __init__(self, project_id: str) -> None:
        self._client = bigquery.Client(project=project_id)
        self._table = f"{project_id}.{_TABLE_ID}"

    def log(self, result: RunResult) -> None:
        row = {
            "source": result.source,
            "run_id": result.run_id,
            "file_count": result.file_count,
            "byte_count": result.byte_count,
            "row_count": result.row_count,
            "status": result.status,
            "error_message": result.error_message,
            "ingested_at": result.ingested_at.isoformat(),
        }
        try:
            errors = self._client.insert_rows_json(self._table, [row])
            if errors:
                log.warning("ingestion_log_insert_failed", errors=errors)
        except Exception:
            # Never let a logging failure propagate — table may not exist yet (pre-terraform apply).
            log.warning("ingestion_log_insert_failed", exc_info=True)
