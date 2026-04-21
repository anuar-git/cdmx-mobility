import uuid
from unittest.mock import MagicMock, patch

from ingestion.bq_logger import IngestionLogger, RunResult


def _make_logger() -> IngestionLogger:
    with patch("google.cloud.bigquery.Client"):
        return IngestionLogger(project_id="test-project")


# --- RunResult defaults ---


def test_run_result_default_status():
    r = RunResult(source="test")
    assert r.status == "success"


def test_run_result_default_error_message_is_none():
    r = RunResult(source="test")
    assert r.error_message is None


def test_run_result_default_row_count_is_none():
    r = RunResult(source="test")
    assert r.row_count is None


def test_run_result_run_id_is_valid_uuid():
    r = RunResult(source="test")
    parsed = uuid.UUID(r.run_id)
    assert str(parsed) == r.run_id


def test_run_result_run_ids_are_unique():
    a = RunResult(source="test")
    b = RunResult(source="test")
    assert a.run_id != b.run_id


# --- IngestionLogger.log ---


def test_log_calls_insert_rows_json():
    logger = _make_logger()
    logger._client.insert_rows_json = MagicMock(return_value=[])

    logger.log(RunResult(source="metro_affluence", file_count=2, byte_count=500))

    logger._client.insert_rows_json.assert_called_once()


def test_log_passes_correct_table():
    logger = _make_logger()
    logger._client.insert_rows_json = MagicMock(return_value=[])

    logger.log(RunResult(source="test"))

    table_arg = logger._client.insert_rows_json.call_args[0][0]
    assert table_arg == "test-project.meta_cdmx.ingestion_log"


def test_log_row_contains_required_fields():
    logger = _make_logger()
    logger._client.insert_rows_json = MagicMock(return_value=[])

    result = RunResult(source="ecobici_station_status", file_count=1, byte_count=200, row_count=50)
    logger.log(result)

    row = logger._client.insert_rows_json.call_args[0][1][0]
    assert row["source"] == "ecobici_station_status"
    assert row["status"] == "success"
    assert row["file_count"] == 1
    assert row["byte_count"] == 200
    assert row["row_count"] == 50
    assert row["error_message"] is None
    assert row["run_id"] == result.run_id


def test_log_does_not_raise_on_row_errors():
    logger = _make_logger()
    logger._client.insert_rows_json = MagicMock(return_value=[{"index": 0, "errors": ["quota"]}])

    # must not raise — logging failure must not fail the pipeline
    logger.log(RunResult(source="test"))


def test_log_does_not_raise_on_api_exception():
    from google.api_core.exceptions import NotFound

    logger = _make_logger()
    logger._client.insert_rows_json = MagicMock(side_effect=NotFound("table not found"))

    # table doesn't exist yet (pre-terraform apply) — must not raise
    logger.log(RunResult(source="test"))


def test_log_error_result():
    logger = _make_logger()
    logger._client.insert_rows_json = MagicMock(return_value=[])

    result = RunResult(source="test", status="error", error_message="connection refused")
    logger.log(result)

    row = logger._client.insert_rows_json.call_args[0][1][0]
    assert row["status"] == "error"
    assert row["error_message"] == "connection refused"
