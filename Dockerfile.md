# Dockerfile

## What it does

Builds the single container image used by all three Cloud Run batch ingestors (metro affluence, EcoBici GBFS, Metrobús GTFS static) and the Metrobús GTFS-RT daemon service. The CLI argument passed at runtime selects which workflow executes — the image itself is agnostic.

### Build stages

1. **Base** — `python:3.11.9-slim` official image.
2. **uv install** — Copies the `uv` binary from the official `ghcr.io/astral-sh/uv:latest` image. This avoids installing uv via pip and keeps the layer small.
3. **Dependency layer** — Copies `pyproject.toml` and `uv.lock` first (before source), runs `uv sync --no-dev --frozen`. This layer is cached until dependencies change.
4. **Source layer** — Copies `ingestion/` and `main.py`. Separated from the dep layer so source changes don't invalidate the dependency cache.

**Entrypoint:** `["uv", "run", "python", "main.py"]`

Cloud Run passes a command override (e.g., `["ingest-ecobici-gbfs"]`) which becomes the Click sub-command.

## Tools used

- **[uv](https://github.com/astral-sh/uv)** — Dependency installation and virtual-env management inside the container.
- **python:3.11.9-slim** — Minimal Debian-based Python image.

## How it ties with the rest of the project

- **[pyproject.toml](pyproject.toml)** + **[uv.lock](uv.lock)** — Installed inside the image at build time.
- **[main.py](main.py)** — Entry point; the Click group that routes to the four ingestors.
- **[infra/modules/cloudrun/main.tf](infra/modules/cloudrun/main.tf)** — References the image URI `us-central1-docker.pkg.dev/cdmx-mobility-prod/ingestor/ingestor:latest` for all Cloud Run resources.
- **[.github/workflows/ci.yml](.github/workflows/ci.yml)** — `build-and-push` job builds this image and pushes it to Artifact Registry on every merge to `main`, tagging with both `latest` and the commit SHA.

### Manual build

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
docker build -t us-central1-docker.pkg.dev/cdmx-mobility-prod/ingestor/ingestor:latest .
docker push us-central1-docker.pkg.dev/cdmx-mobility-prod/ingestor/ingestor:latest
```
