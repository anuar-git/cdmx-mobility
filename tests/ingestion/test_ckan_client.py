from unittest.mock import MagicMock, patch

import pytest

from ingestion.ckan_client import CKANClient

MOCK_RESPONSE = {
    "success": True,
    "result": {
        "resources": [
            {
                "name": "March 2025",
                "format": "CSV",
                "url": "https://example.com/afluencia_2025_03.csv",
            }
        ]
    },
}


def _make_client() -> CKANClient:
    return CKANClient(
        base_url="https://datos.cdmx.gob.mx/api/3/action",
        timeout=10,
        max_retries=1,
    )


def test_get_resources_returns_list():
    client = _make_client()
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client_class:
        mock_client_class.return_value.__enter__.return_value.get.return_value = mock_resp
        resources = client.get_resources("afluencia-preliminar-del-metro-cdmx")

    assert len(resources) == 1
    assert resources[0]["format"] == "CSV"
    assert resources[0]["name"] == "March 2025"


def test_get_resources_raises_on_ckan_error():
    client = _make_client()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": False, "error": {"message": "Not found"}}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client_class:
        mock_client_class.return_value.__enter__.return_value.get.return_value = mock_resp
        with pytest.raises(RuntimeError, match="CKAN error"):
            client.get_resources("bad-dataset-id")


def test_download_resource_returns_bytes():
    client = _make_client()
    mock_resp = MagicMock()
    mock_resp.content = b"col1,col2\n1,2"
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client_class:
        mock_client_class.return_value.__enter__.return_value.get.return_value = mock_resp
        data = client.download_resource("https://example.com/afluencia_2025_03.csv")

    assert data == b"col1,col2\n1,2"
