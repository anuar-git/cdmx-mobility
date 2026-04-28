"""Pipeline health API — FastAPI service querying meta_cdmx and marts_cdmx.

Deployed as a Cloud Run service (pipeline-api). Authentication is handled
by Cloud Run's IAM invoker binding — the dashboard calls this service with
an Identity Token obtained from the GCP metadata server (or a service account
key for local dev).

Endpoints:
  GET /health                        — liveness probe
  GET /api/pipeline/health?days=30   — dim_pipeline_health time series
  GET /api/pipeline/freshness        — latest freshness check per source
  GET /api/pipeline/tests?days=30    — dbt test pass rate time series
  GET /api/pipeline/runtime?days=30  — dbt runtime per run
  GET /api/pipeline/ingestion?days=30 — ingestion row counts per source
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.pipeline import router as pipeline_router

_ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app = FastAPI(
    title="CDMX Mobility — Pipeline Health API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["Authorization"],
)

app.include_router(pipeline_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
