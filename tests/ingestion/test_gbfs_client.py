from unittest.mock import MagicMock, patch

import httpx
import pytest

from ingestion.gbfs_client import GBFSClient

MOCK_FEED = {
    "last_updated": 1700000000,
    "ttl": 60,
    "data": {"stations": [{"station_id": "1", "num_bikes_available": 5}]},
}


def _make_client(api_key: str = "") -> GBFSClient:
    return GBFSClient(
        base_url="https://gbfs.example.com/gbfs/es",
        timeout=10,
        max_retries=1,
        api_key=api_key,
    )


def test_fetch_returns_parsed_json():
    client = _make_client()
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_FEED
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client_class:
        mock_client_class.return_value.__enter__.return_value.get.return_value = mock_resp
        result = client.fetch("station_status")

    assert result["last_updated"] == 1700000000
    assert result["data"]["stations"][0]["station_id"] == "1"


def test_fetch_raises_on_http_error():
    client = _make_client()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found", request=MagicMock(), response=MagicMock()
    )

    with patch("httpx.Client") as mock_client_class:
        mock_client_class.return_value.__enter__.return_value.get.return_value = mock_resp
        with pytest.raises(httpx.HTTPStatusError):
            client.fetch("station_status")


def test_fetch_sends_bearer_token_when_api_key_set():
    client = _make_client(api_key="secret-key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_FEED
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client_class:
        mock_get = mock_client_class.return_value.__enter__.return_value.get
        mock_get.return_value = mock_resp
        client.fetch("station_status")

    assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer secret-key"


def test_fetch_sends_no_auth_header_when_no_api_key():
    client = _make_client(api_key="")
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_FEED
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client_class:
        mock_get = mock_client_class.return_value.__enter__.return_value.get
        mock_get.return_value = mock_resp
        client.fetch("station_status")

    assert mock_get.call_args.kwargs["headers"] == {}
