from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CDMX_", env_file=".env")

    gcp_project_id: str
    raw_bucket_name: str = "cdmx-mobility-raw"
    metro_ckan_base_url: str = "https://datos.cdmx.gob.mx/api/3/action"
    metro_affluence_dataset_id: str = "afluencia-diaria-del-metro-cdmx"
    http_timeout_seconds: int = 30
    http_max_retries: int = 3

    ecobici_gbfs_base_url: str = "https://gbfs.mex.lyftbikes.com/gbfs/es"
    ecobici_api_key: str = ""
    ecobici_poll_feeds: list[str] = ["station_information", "station_status", "system_alerts"]

    # Metrobús GTFS-Realtime — dormant; gtfs_rt.py retained in repo pending a direct SEMOVI URL
    metrobus_gtfs_rt_vehicle_positions_url: str = ""
    metrobus_gtfs_rt_poll_interval_seconds: int = 30

    # Metrobús GTFS email delivery — sinopticoplus.com
    # JWT and Outlook app password are stored in Secret Manager (metrobus_sinoptico_jwt,
    # outlook_imap_app_password). No env vars needed beyond gcp_project_id.
    # Override to route the sinopticoplus email to the SendGrid inbound address
    # (e.g. gtfs@inbound.anuarhage.com). Defaults to the JWT account email.
    metrobus_sinoptico_recipient_email: str = ""
    # Secret token embedded in the webhook URL path — set via env var on the Cloud Run Service
    metrobus_inbound_webhook_secret: str = ""

    # Open-Meteo weather API — free, no auth required.
    # Points at the forecast endpoint which supports historical dates up to 92 days back.
    weather_openmeteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
