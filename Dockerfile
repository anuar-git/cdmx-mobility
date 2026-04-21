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

ENTRYPOINT ["uv", "run", "python", "main.py"]
