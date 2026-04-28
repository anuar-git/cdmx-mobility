FROM python:3.11-slim

WORKDIR /app

# Install only the runtime deps needed by the API — not spark or dev groups.
COPY pyproject.toml uv.lock* ./
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-dev \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.30.0" \
        "google-cloud-bigquery>=3.25.0"

COPY api/ ./

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
