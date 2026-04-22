FROM python:3.11.9-slim

# Copy the uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install dependencies before copying source to maximise layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Copy application source
COPY ingestion/ ingestion/
COPY main.py ./

# UV_NO_SYNC: tell `uv run` to use the venv as-is without re-syncing.
# Without this, `uv run` syncs to the full lockfile (including dev/spark groups)
# on every container start, downloading and installing lint/test tools at runtime.
ENV UV_NO_SYNC=1

ENTRYPOINT ["uv", "run", "python", "main.py"]
