# .github/workflows/ci.yml

## What it does

Defines the GitHub Actions CI/CD pipeline. It runs on every pull request and on every push to `main`. The pipeline validates code quality, authenticates to GCP, runs live data ingestors, and builds and publishes the Docker image.

## Jobs

### `lint-and-test` (all branches)

Runs on every PR and push. Gates all downstream main-only jobs.

1. Installs Python 3.11.9 and all dependency groups via `uv sync --all-groups`.
2. `ruff check .` — Python linting.
3. `black --check .` — Python formatting.
4. `sqlfluff lint dbt_bigquery/models --dialect bigquery` — SQL linting.
5. `pytest tests/ -v` — Full unit test suite.

### `terraform-validate` (all branches)

1. Installs Terraform 1.9.5.
2. `terraform fmt -check -recursive` — Validates formatting.
3. `terraform init -backend=false` — Initializes without connecting to GCS state backend.
4. `terraform validate` — Validates HCL syntax and module references.

### `gcp-auth-smoke-test` (main only)

Verifies that Workload Identity Federation (WIF) authentication is functional.

1. Authenticates using `google-github-actions/auth@v2` with `WIF_PROVIDER` and `GCP_SERVICE_ACCOUNT` secrets.
2. Runs `gcloud auth list && gcloud config list` to confirm the token is valid.

### `ingest-metro` (main only, needs: `lint-and-test`)

Runs the metro affluence ingestor against the live GCP project on every merge.

```bash
CDMX_GCP_PROJECT_ID=cdmx-mobility-prod
CDMX_RAW_BUCKET_NAME=cdmx-mobility-raw
uv run python main.py ingest-metro-affluence
```

### `ingest-metrobus-static` (main only, needs: `lint-and-test`)

Runs the Metrobús GTFS static ingestor against the live GCP project on every merge.

```bash
CDMX_GCP_PROJECT_ID=cdmx-mobility-prod
CDMX_RAW_BUCKET_NAME=cdmx-mobility-raw
CDMX_METROBUS_GTFS_STATIC_DATASET_ID=gtfs
uv run python main.py ingest-metrobus-gtfs-static
```

### `build-and-push` (main only, needs: `lint-and-test`)

Builds and publishes the ingestor Docker image to Artifact Registry.

1. Authenticates with WIF.
2. `gcloud auth configure-docker us-central1-docker.pkg.dev`.
3. `docker build` — tags with both `latest` and the commit SHA.
4. `docker push` — pushes both tags to `us-central1-docker.pkg.dev/cdmx-mobility-prod/ingestor/ingestor`.

## Permissions

- `contents: read` — checkout access.
- `id-token: write` — required for OIDC token exchange (Workload Identity Federation).

## Required secrets

| Secret | Used by |
|---|---|
| `WIF_PROVIDER` | All GCP auth steps |
| `GCP_SERVICE_ACCOUNT` | All GCP auth steps |

## How it ties with the rest of the project

- **[main.py](main.py)** — CLI commands invoked by the ingestor jobs.
- **[Dockerfile](Dockerfile)** — Image built and pushed by `build-and-push`.
- **[infra/modules/iam/main.tf](infra/modules/iam/main.tf)** — Provisions the WIF pool and service account that CI authenticates with.
- **[infra/modules/cloudrun/main.tf](infra/modules/cloudrun/main.tf)** — The image pushed here is referenced by Cloud Run resources.
- **[pyproject.toml](pyproject.toml)** — Provides tool configuration for ruff, black, and pytest.
