.PHONY: help install fmt lint test ci-local \
        tf-init tf-plan tf-apply tf-destroy \
        ingest-ecobici ingest-metro ingest-weather \
        spark-local dbt-build dbt-test \
        clean

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

clean: ## Remove caches and temp files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	rm -rf .coverage htmlcov/
