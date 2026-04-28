#!/usr/bin/env bash
# bootstrap_connections.sh — run once after `docker compose up` to create all
# Airflow Connections and Variables.  Reads secrets from GCP Secret Manager;
# no credentials are stored in this file.
#
# Usage (from orchestration/):
#   bash bootstrap_connections.sh
set -euo pipefail

PROJECT="cdmx-mobility-prod"
COMPOSE="docker compose"

echo "==> Waiting for Airflow webserver to be healthy..."
until ${COMPOSE} exec -T airflow-webserver curl -sf http://localhost:8080/health | grep -q '"healthy"'; do
  sleep 5
done
echo "    Webserver is up."

# ── Connections ───────────────────────────────────────────────────────────────

echo "==> Creating google_cloud_default connection..."
${COMPOSE} exec -T airflow-scheduler airflow connections delete google_cloud_default 2>/dev/null || true
${COMPOSE} exec -T airflow-scheduler airflow connections add google_cloud_default \
  --conn-type google_cloud_platform \
  --conn-extra "{\"project\": \"${PROJECT}\", \"num_retries\": 5}"

echo "==> Creating slack_cdmx connection..."
SLACK_URL=$(gcloud secrets versions access latest \
  --secret=airflow-slack-webhook-url --project="${PROJECT}")
${COMPOSE} exec -T airflow-scheduler airflow connections delete slack_cdmx 2>/dev/null || true
${COMPOSE} exec -T airflow-scheduler airflow connections add slack_cdmx \
  --conn-type http \
  --conn-host "${SLACK_URL}"

# ── Variables ────────────────────────────────────────────────────────────────

echo "==> Setting Airflow Variables..."
${COMPOSE} exec -T airflow-scheduler airflow variables set GCP_PROJECT      "${PROJECT}"
${COMPOSE} exec -T airflow-scheduler airflow variables set GCS_DATA_BUCKET  "cdmx-mobility-data"
${COMPOSE} exec -T airflow-scheduler airflow variables set GCS_RAW_BUCKET   "cdmx-mobility-raw"
${COMPOSE} exec -T airflow-scheduler airflow variables set AIRFLOW_ENV      "production"

echo ""
echo "==> Done. Connections and Variables are set."
echo "    Open the UI at http://localhost:8080 (admin/admin on first boot)."
