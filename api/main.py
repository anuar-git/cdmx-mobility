"""CDMX Mobility API — FastAPI service querying meta_cdmx and marts_cdmx.

Deployed as a Cloud Run service (pipeline-api). Authentication is handled
by Cloud Run's IAM invoker binding — the dashboard calls this service with
an Identity Token obtained from the GCP metadata server (or a service account
key for local dev).

Endpoints:
  GET /health                              — liveness probe

  Pipeline health (Phase 5):
  GET /api/pipeline/health?days=30         — dim_pipeline_health time series
  GET /api/pipeline/freshness             — latest freshness check per source
  GET /api/pipeline/tests?days=30         — dbt test pass rate time series
  GET /api/pipeline/runtime?days=30       — dbt runtime per run
  GET /api/pipeline/ingestion?days=30     — ingestion row counts per source

  Analytical dashboards (Phase 6):
  GET /api/pulse/ridership?days=8         — daily ridership per mode
  GET /api/pulse/stockout?limit=10        — top-N stressed EcoBici stations today
  GET /api/pulse/weather                  — latest city-wide weather observation

  GET /api/station/list                   — all stations (lat/lon/mode)
  GET /api/station/{id}/hourly?days=30    — hourly EcoBici demand time-series
  GET /api/station/{id}/weather-scatter   — daily (temperature, trips) pairs
  GET /api/station/{id}/neighbors         — stations within radius_m metres
  GET /api/station/{id}/forecast          — 24-hour ahead same-hour average

  GET /api/modal/lines                    — Metro lines with ridership summary
  GET /api/modal/substitution?line=X      — substitution time-series for a line
  GET /api/modal/corridor?line=X          — stations in a line's 300 m corridor

  GET /api/equity/scores                  — station-level accessibility scores
  GET /api/equity/stockout-by-borough     — avg stockout minutes per station
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.equity import router as equity_router
from routers.modal import router as modal_router
from routers.pipeline import router as pipeline_router
from routers.pulse import router as pulse_router
from routers.station import router as station_router

_ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app = FastAPI(
    title="CDMX Mobility API",
    version="2.0.0",
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
app.include_router(pulse_router)
app.include_router(station_router)
app.include_router(modal_router)
app.include_router(equity_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
