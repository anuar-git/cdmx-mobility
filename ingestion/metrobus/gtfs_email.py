"""Metrobús GTFS email trigger — sinopticoplus.com.

Refreshes the 24-h JWT and POSTs to sinopticoplus to trigger email delivery
to the inbound.anuarhage.com address (handled by the inbound_webhook service).

Workflow:
  1. Load stored JWT from Secret Manager.
  2. GET /gtfs-api/validateEmailMetrobus/{email} → fresh JWT in response header.
  3. Persist fresh JWT as a new Secret Manager version.
  4. POST /gtfs-api/senderEmailGtfs/{client_id}/{recipient} → email sent.
  5. Log RunResult to meta_cdmx.ingestion_log.
"""

import base64
import json

import httpx
import structlog
from google.cloud import secretmanager

from ingestion.bq_logger import IngestionLogger, RunResult
from ingestion.config import Settings

log = structlog.get_logger()

_SINOPTICO_BASE = "https://metrobus-gtfs.sinopticoplus.com"


def _decode_jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _load_secret(project_id: str, secret_id: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    return client.access_secret_version(request={"name": name}).payload.data.decode()


def _store_secret(project_id: str, secret_id: str, value: str) -> None:
    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{project_id}/secrets/{secret_id}"
    new_version = client.add_secret_version(
        request={"parent": parent, "payload": {"data": value.encode()}}
    )
    # Destroy only versions older than the one we just created — each active
    # version is billed at $0.06/month (288 updates/day). Comparing by version
    # number (not name equality) prevents concurrent executions from destroying
    # each other's newly-written versions.
    new_version_num = int(new_version.name.split("/")[-1])
    for version in client.list_secret_versions(request={"parent": parent}):
        if int(version.name.split("/")[-1]) < new_version_num and int(version.state) != 3:
            client.destroy_secret_version(request={"name": version.name})


def _refresh_jwt(current_jwt: str, email: str, timeout: int) -> str:
    url = f"{_SINOPTICO_BASE}/gtfs-api/validateEmailMetrobus/{email}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers={"Authorization": f"Bearer {current_jwt}"})
        resp.raise_for_status()
    fresh = resp.headers.get("authorization")
    if not fresh:
        raise ValueError("validateEmailMetrobus: missing authorization in response headers")
    return fresh


def _trigger_email(client_id: int, recipient: str, jwt: str, timeout: int) -> None:
    url = f"{_SINOPTICO_BASE}/gtfs-api/senderEmailGtfs/{client_id}/{recipient}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers={"Authorization": f"Bearer {jwt}"})
        resp.raise_for_status()
    log.info("email_triggered", client_id=client_id, recipient=recipient)


def run(settings: Settings) -> None:
    result = RunResult(source="metrobus_gtfs_email_trigger")
    bq_logger = IngestionLogger(project_id=settings.gcp_project_id)

    try:
        current_jwt = _load_secret(settings.gcp_project_id, "metrobus_sinoptico_jwt")
        claims = _decode_jwt_claims(current_jwt)
        account_email: str = claims["email"]
        client_id: int = claims["idCliente"]

        fresh_jwt = _refresh_jwt(current_jwt, account_email, settings.http_timeout_seconds)
        _store_secret(settings.gcp_project_id, "metrobus_sinoptico_jwt", fresh_jwt)
        log.info("jwt_refreshed", client_id=client_id)

        recipient = settings.metrobus_sinoptico_recipient_email or account_email
        _trigger_email(client_id, recipient, fresh_jwt, settings.http_timeout_seconds)

    except Exception as exc:
        result.status = "error"
        result.error_message = str(exc)
        log.exception("gtfs_email_trigger_failed")
        raise

    finally:
        bq_logger.log(result)
