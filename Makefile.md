# Makefile

## What it does

Provides convenience `make` targets that wrap the common developer workflows — dependency installation, formatting, linting, testing, Terraform operations, ingestion runs, and dbt commands. All Python operations are prefixed with `uv run` per project convention.

Run `make help` to see all targets with descriptions.

## Targets

### Development

| Target | What it does |
|---|---|
| `install` | `uv sync --all-groups` + `pre-commit install` |
| `fmt` | `ruff format`, `black`, and `terraform fmt -recursive` |
| `lint` | `ruff check`, `sqlfluff lint` (BigQuery), `terraform fmt -check`, `terraform validate` |
| `test` | `pytest tests/ -v` |
| `ci-local` | Runs `fmt lint test` in sequence — replicates the CI pipeline locally |
| `clean` | Removes `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.coverage`, `htmlcov/` |

### Terraform

| Target | What it does |
|---|---|
| `tf-init` | `terraform init` inside `infra/` |
| `tf-plan` | `terraform plan -out=tfplan` inside `infra/` |
| `tf-apply` | `terraform apply tfplan` inside `infra/` |
| `tf-destroy` | `terraform destroy` — destroys all infra (destructive!) |

### Ingestion (local one-shot runs)

| Target | What it does |
|---|---|
| `ingest-ecobici` | `uv run python -m ingestion.ecobici` |
| `ingest-metro` | `uv run python -m ingestion.metro` |

### Analytics

| Target | What it does |
|---|---|
| `spark-local` | Runs a local Spark job via `spark_jobs.local_runner` (requires `--group spark`) |
| `dbt-build` | `dbt build` inside `dbt_bigquery/` |
| `dbt-test` | `dbt test` inside `dbt_bigquery/` |

## How it ties with the rest of the project

- **[pyproject.toml](pyproject.toml)** — Defines the tools (`ruff`, `black`, `pytest`, `sqlfluff`) that Makefile targets invoke.
- **[infra/](infra/)** — Terraform targets operate on this directory.
- **[dbt_bigquery/](dbt_bigquery/)** — dbt targets `cd` into this directory before running.
- **[.pre-commit-config.yaml](.pre-commit-config.yaml)** — Installed by `make install`; mirrors the lint checks in `make lint`.
