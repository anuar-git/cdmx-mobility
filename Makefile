.PHONY: help install fmt lint test ci-local \
        tf-init tf-plan tf-apply tf-destroy \
        ingest-ecobici ingest-metro ingest-weather \
        spark-local dbt-build dbt-test \
        airflow-up airflow-down airflow-logs airflow-status \
        backfill backfill-range \
        clean

# ── Airflow VM helper ─────────────────────────────────────────────────────────
_AIRFLOW_IP = $(shell cd infra && terraform output -raw airflow_vm_ip 2>/dev/null || echo "")
_SSH = gcloud compute ssh cdmx-airflow \
	--project=cdmx-mobility-prod \
	--zone=us-central1-a \
	--tunnel-through-iap \
	--
_COMPOSE = docker compose -f /opt/cdmx-mobility/orchestration/docker-compose.yml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all Python dependencies via uv
	uv sync --all-groups
	pre-commit install

fmt: ## Format code
	uv run ruff format .
	uv run black .
	cd infra && terraform fmt -recursive

lint: ## Lint everything
	uv run ruff check .
	uv run sqlfluff lint dbt_bigquery/models --dialect bigquery
	cd infra && terraform fmt -check -recursive
	cd infra && terraform validate

test: ## Run unit tests
	uv run pytest tests/ -v

ci-local: fmt lint test ## Run the full CI pipeline locally

tf-init: ## Initialize Terraform
	cd infra && terraform init

tf-plan: ## Show Terraform plan
	cd infra && terraform plan -out=tfplan

tf-apply: ## Apply Terraform plan
	cd infra && terraform apply tfplan

tf-destroy: ## Destroy all infrastructure (careful!)
	cd infra && terraform destroy

ingest-ecobici: ## Run EcoBici ingestion
	uv run python -m ingestion.ecobici

ingest-metro: ## Run Metro affluence ingestion
	uv run python -m ingestion.metro

ingest-weather: ## Run weather ingestion
	uv run python -m ingestion.weather

spark-local: ## Run a Spark job locally against sample data
	uv run --group spark python -m spark_jobs.local_runner

dbt-build: ## Run dbt build
	cd dbt_bigquery && uv run dbt build

dbt-test: ## Run dbt tests
	cd dbt_bigquery && uv run dbt test

airflow-up: ## Start Airflow on the VM via Docker Compose
	$(_SSH) "cd /opt/cdmx-mobility && git pull --ff-only origin main && $(_COMPOSE) up -d"

airflow-down: ## Stop Airflow on the VM
	$(_SSH) "$(_COMPOSE) down"

airflow-logs: ## Tail Airflow scheduler logs (Ctrl-C to stop)
	$(_SSH) "$(_COMPOSE) logs -f --tail=100 airflow-scheduler"

airflow-status: ## Show Airflow container status on the VM
	$(_SSH) "$(_COMPOSE) ps"

airflow-shell: ## Open a shell in the Airflow scheduler container
	$(_SSH) "$(_COMPOSE) exec airflow-scheduler bash"

# ── Backfill ──────────────────────────────────────────────────────────────────
# Trigger a one-day backfill end-to-end via the Airflow REST API (over IAP tunnel).
#
# Usage:
#   make backfill DATE=2026-03-15
#
# The command opens an IAP SSH tunnel in the background (port 18080 → VM:8080),
# posts the DAG trigger via curl, then closes the tunnel.
backfill: ## Trigger a one-day backfill. Usage: make backfill DATE=YYYY-MM-DD
	@test -n "$(DATE)" || (echo "ERROR: DATE is required. Usage: make backfill DATE=YYYY-MM-DD" && exit 1)
	@echo "==> Opening IAP tunnel on localhost:18080..."
	@gcloud compute ssh cdmx-airflow \
		--project=cdmx-mobility-prod \
		--zone=us-central1-a \
		--tunnel-through-iap \
		-- -L 18080:localhost:8080 -N -f -o ExitOnForwardFailure=yes
	@sleep 2
	@echo "==> Triggering daily_mobility_pipeline for $(DATE)..."
	@curl -sf -X POST "http://localhost:18080/api/v1/dags/daily_mobility_pipeline/dagRuns" \
		-H "Content-Type: application/json" \
		-u "admin:admin" \
		-d "{\"dag_run_id\": \"backfill_$(DATE)\", \"logical_date\": \"$(DATE)T08:00:00Z\"}"
	@echo ""
	@echo "==> Backfill triggered. Monitor at http://localhost:18080"
	@echo "    (IAP tunnel is open on localhost:18080 — kill it when done: pkill -f 'L 18080')"

backfill-range: ## Backfill a date range. Usage: make backfill-range START=2026-03-01 END=2026-03-31
	@test -n "$(START)" || (echo "ERROR: START required. Usage: make backfill-range START=YYYY-MM-DD END=YYYY-MM-DD" && exit 1)
	@test -n "$(END)"   || (echo "ERROR: END required."   && exit 1)
	@echo "==> Backfilling $(START) → $(END)..."
	@gcloud compute ssh cdmx-airflow \
		--project=cdmx-mobility-prod \
		--zone=us-central1-a \
		--tunnel-through-iap \
		-- -L 18080:localhost:8080 -N -f -o ExitOnForwardFailure=yes
	@sleep 2
	@d=$(START); while [ "$$d" != "$$(date -d '$(END) + 1 day' +%Y-%m-%d)" ]; do \
		echo "  Triggering $$d..."; \
		curl -sf -X POST "http://localhost:18080/api/v1/dags/daily_mobility_pipeline/dagRuns" \
			-H "Content-Type: application/json" \
			-u "admin:admin" \
			-d "{\"dag_run_id\": \"backfill_$$d\", \"logical_date\": \"$${d}T08:00:00Z\"}" \
			> /dev/null; \
		d=$$(date -d "$$d + 1 day" +%Y-%m-%d); \
		sleep 1; \
	done
	@echo "==> All backfill runs triggered. Monitor at http://localhost:18080"

clean: ## Remove caches and temp files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	rm -rf .coverage htmlcov/
