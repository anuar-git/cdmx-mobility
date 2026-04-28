#!/bin/bash
# Startup script for the Airflow VM.
# Runs once on first boot (and on each reboot).
set -euxo pipefail

PROJECT="cdmx-mobility-prod"

# ── Docker ────────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable docker
systemctl start docker

# Ensure the default user is in the docker group.
MAIN_USER=$(getent passwd 1000 | cut -d: -f1 || echo "debian")
usermod -aG docker "${MAIN_USER}" || true

# ── gcloud SDK ────────────────────────────────────────────────────────────────
if ! command -v gcloud &>/dev/null; then
  apt-get install -y apt-transport-https ca-certificates gnupg
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | tee /etc/apt/sources.list.d/google-cloud-sdk.list
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
  apt-get update && apt-get install -y google-cloud-cli
fi

# ── Repo clone ────────────────────────────────────────────────────────────────
REPO_DIR="/opt/cdmx-mobility"
if [ ! -d "${REPO_DIR}/.git" ]; then
  git clone "${REPO_URL:-https://github.com/anuar-git/cdmx-mobility.git}" "${REPO_DIR}"
fi

# ── Pull secrets from Secret Manager ─────────────────────────────────────────
FERNET=$(gcloud secrets versions access latest \
  --secret=airflow-fernet-key --project="${PROJECT}" 2>/dev/null || echo "")
DB_PASS=$(gcloud secrets versions access latest \
  --secret=airflow-db-password --project="${PROJECT}" 2>/dev/null || echo "airflow")
SLACK_URL=$(gcloud secrets versions access latest \
  --secret=airflow-slack-webhook-url --project="${PROJECT}" 2>/dev/null || echo "")

# ── Write .env consumed by Docker Compose ────────────────────────────────────
cat > "${REPO_DIR}/orchestration/.env" <<EOF
AIRFLOW__CORE__FERNET_KEY=${FERNET}
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:${DB_PASS}@postgres/airflow
AIRFLOW__CORE__EXECUTOR=LocalExecutor
AIRFLOW__CORE__LOAD_EXAMPLES=false
AIRFLOW__WEBSERVER__SECRET_KEY=${FERNET}
SLACK_WEBHOOK_URL=${SLACK_URL}
GCP_PROJECT_ID=${PROJECT}
GCS_DATA_BUCKET=cdmx-mobility-data
GCS_RAW_BUCKET=cdmx-mobility-raw
EOF

# Write DB password for the Docker secret file.
echo -n "${DB_PASS}" > "${REPO_DIR}/orchestration/.db_password"
chmod 600 "${REPO_DIR}/orchestration/.db_password"

# ── Start Airflow ─────────────────────────────────────────────────────────────
cd "${REPO_DIR}/orchestration"
docker compose pull --quiet || true
docker compose up -d

# ── DAG sync cron: git pull every 5 min, restart scheduler ───────────────────
cat > /etc/cron.d/airflow-dag-sync <<'CRON'
*/5 * * * * root \
  cd /opt/cdmx-mobility && \
  git pull --ff-only origin main 2>/dev/null && \
  docker compose -f /opt/cdmx-mobility/orchestration/docker-compose.yml \
    restart airflow-scheduler 2>/dev/null || true
CRON
chmod 644 /etc/cron.d/airflow-dag-sync
