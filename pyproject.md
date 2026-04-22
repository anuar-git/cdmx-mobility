# pyproject.toml

## What it does

`pyproject.toml` is the project manifest for the `cdmx-mobility` Python package. It governs:

- **Runtime dependencies** — libraries required by the ingestion code in production.
- **Dev dependency group** — testing, linting, and formatting tools used locally and in CI.
- **Spark dependency group** — PySpark + Delta Lake for Dataproc jobs (optional, installed with `uv sync --group spark`).
- **Tool configuration** — lint rules for `ruff` and `black`, and pytest settings.

## Dependencies

### Runtime (`dependencies`)

| Package | Purpose |
|---|---|
| `click` | CLI framework used by `main.py` |
| `httpx` | Async-capable HTTP client used by `CKANClient`, `GBFSClient`, and GTFS-RT fetcher |
| `tenacity` | Retry decorator for all HTTP calls |
| `pydantic` / `pydantic-settings` | Settings model with env-var binding (`CDMX_` prefix) |
| `google-cloud-storage` | GCS uploads via `GCSUploader` |
| `google-cloud-bigquery` | Ingestion log writes via `IngestionLogger` |
| `google-cloud-secret-manager` | Secret Manager access (Cloud Run secrets) |
| `structlog` | Structured JSON logging across all modules |
| `dbt-bigquery` | dbt CLI + BigQuery adapter for `dbt_bigquery/` models |
| `gtfs-realtime-bindings` | GTFS-RT protobuf Python bindings |
| `protobuf` | Protobuf deserialization + `MessageToDict` conversion |

### Dev group (`dependency-groups.dev`)

`pytest`, `pytest-cov`, `ruff`, `black`, `mypy`, `sqlfluff`, `pre-commit`

### Spark group (`dependency-groups.spark`)

`pyspark==3.5.2`, `chispa`, `delta-spark` — for Dataproc/local Spark jobs.

## Tool configuration

- **ruff** — line length 100, Python 3.11 target, rules: E, F, I, N, W, UP, B, SIM, RUF.
- **black** — line length 100, Python 3.11 target.
- **pytest** — test root `tests/`, coverage on `ingestion` and `spark_jobs` packages, strict markers, verbose output.

## How it ties with the rest of the project

- **uv** reads this file to resolve and lock dependencies (`uv.lock`).
- **[Dockerfile](Dockerfile)** runs `uv sync --no-dev --frozen` from this file to install only runtime deps.
- **[CI](.github/workflows/ci.yml)** runs `uv sync --all-groups` to install all dependency groups before linting and testing.
- **[Makefile](Makefile)** `install` target runs `uv sync --all-groups && pre-commit install`.
- **[.pre-commit-config.yaml](.pre-commit-config.yaml)** invokes ruff and black hooks whose configuration is defined here.
