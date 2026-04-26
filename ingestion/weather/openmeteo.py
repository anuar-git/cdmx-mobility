"""Open-Meteo weather ingestor.

Fetches hourly weather for 5 representative CDMX coordinates from the
Open-Meteo free API (no authentication required). Runs daily at 02:00 CDMX
time and fetches the prior calendar day so that a full 24-hour UTC day is
always available.

The 5 coordinates cover the geographic spread of Metrobús and Metro routes:
  centro      — downtown ZMVM centroid (Zócalo area)
  aeropuerto  — eastern edge (AICM, terminal of Line 5)
  pedregal    — southern edge (end of Line 3)
  tlalnepantla — northern edge (Estado de México, Metrobús Line 2)
  ecatepec    — north-eastern edge (Estado de México, Line B extension)

Wind speed is requested in m/s (wind_speed_unit=ms) for consistency with the
Spark Silver job's Beaufort-scale wind category thresholds.

Output — NDJSON: one JSON line per coordinate, uploaded as a single file.
Each line schema:
  coordinate_id (str), latitude (float), longitude (float),
  fetch_date (YYYY-MM-DD), hourly (object with parallel arrays:
    time, temperature_2m, precipitation, windspeed_10m, relativehumidity_2m)

GCS path: weather/hourly/ingestion_date=YYYY-MM-DD/weather_YYYY-MM-DD.json
"""

import datetime
import json

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ingestion.bq_logger import IngestionLogger, RunResult
from ingestion.config import Settings
from ingestion.gcs_uploader import GCSUploader

log = structlog.get_logger()

_HOURLY_VARIABLES = [
    "temperature_2m",
    "precipitation",
    "windspeed_10m",
    "relativehumidity_2m",
]

COORDINATES = [
    {"id": "centro", "lat": 19.4326, "lon": -99.1332},
    {"id": "aeropuerto", "lat": 19.4363, "lon": -99.0721},
    {"id": "pedregal", "lat": 19.3204, "lon": -99.1929},
    {"id": "tlalnepantla", "lat": 19.5442, "lon": -99.1963},
    {"id": "ecatepec", "lat": 19.6008, "lon": -99.0325},
]


class OpenMeteoClient:
    def __init__(self, base_url: str, timeout: int, max_retries: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def fetch(self, lat: float, lon: float, date: str) -> dict:
        return self._fetch(lat, lon, date)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
    def _fetch(self, lat: float, lon: float, date: str) -> dict:
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(_HOURLY_VARIABLES),
            "start_date": date,
            "end_date": date,
            "timezone": "UTC",
            "temperature_unit": "celsius",
            "wind_speed_unit": "ms",
        }
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(self._base_url, params=params)
            response.raise_for_status()
        return response.json()


def _validate(payload: dict, coordinate_id: str) -> None:
    """Raise ValueError if the response is missing expected hourly arrays."""
    hourly = payload.get("hourly", {})
    if not hourly.get("time"):
        raise ValueError(f"Open-Meteo response for {coordinate_id!r} missing hourly.time")
    for var in _HOURLY_VARIABLES:
        if var not in hourly:
            raise ValueError(f"Open-Meteo response for {coordinate_id!r} missing hourly.{var}")


def run(settings: Settings) -> None:
    bq_logger = IngestionLogger(project_id=settings.gcp_project_id)
    result = RunResult(source="weather_openmeteo")

    try:
        client = OpenMeteoClient(
            base_url=settings.weather_openmeteo_base_url,
            timeout=settings.http_timeout_seconds,
            max_retries=settings.http_max_retries,
        )
        uploader = GCSUploader(bucket_name=settings.raw_bucket_name)

        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

        lines: list[str] = []
        total_hours = 0

        for coord in COORDINATES:
            log.info("fetching_weather", coordinate=coord["id"], date=yesterday)
            payload = client.fetch(lat=coord["lat"], lon=coord["lon"], date=yesterday)
            _validate(payload, coord["id"])

            line_dict = {
                "coordinate_id": coord["id"],
                "latitude": coord["lat"],
                "longitude": coord["lon"],
                "fetch_date": yesterday,
                "hourly": {
                    "time": payload["hourly"]["time"],
                    "temperature_2m": payload["hourly"]["temperature_2m"],
                    "precipitation": payload["hourly"]["precipitation"],
                    "windspeed_10m": payload["hourly"]["windspeed_10m"],
                    "relativehumidity_2m": payload["hourly"]["relativehumidity_2m"],
                },
            }
            lines.append(json.dumps(line_dict))
            total_hours += len(payload["hourly"]["time"])

        ndjson_bytes = "\n".join(lines).encode("utf-8")
        gcs_path = f"weather/hourly/ingestion_date={yesterday}/weather_{yesterday}.json"
        destination = uploader.upload(ndjson_bytes, gcs_path, content_type="application/x-ndjson")
        log.info(
            "uploaded_weather",
            destination=destination,
            coordinates=len(lines),
            total_hours=total_hours,
        )

        result.file_count = 1
        result.byte_count = len(ndjson_bytes)
        result.row_count = total_hours

    except Exception as exc:
        result.status = "error"
        result.error_message = str(exc)
        raise

    finally:
        bq_logger.log(result)
