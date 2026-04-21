import click

from ingestion.config import Settings
from ingestion.ecobici import gbfs as ecobici_gbfs
from ingestion.metro import affluence
from ingestion.metrobus import gtfs_email as metrobus_gtfs_email
from ingestion.metrobus import gtfs_rt as metrobus_gtfs_rt
from ingestion.metrobus import gtfs_static as metrobus_gtfs_static
from ingestion.metrobus import inbound_webhook as metrobus_inbound_webhook
from ingestion.weather import openmeteo as weather_openmeteo


@click.group()
def cli() -> None:
    pass


@cli.command()
def ingest_metro_affluence() -> None:
    """Download metro affluence CSVs and land them in GCS."""
    settings = Settings()
    affluence.run(settings)


@cli.command()
def ingest_ecobici_gbfs() -> None:
    """Poll EcoBici GBFS feeds and land them in GCS."""
    settings = Settings()
    ecobici_gbfs.run(settings)


@cli.command()
def ingest_metrobus_gtfs_static() -> None:
    """Download the SEMOVI CDMX GTFS static ZIP and land each feed CSV in GCS."""
    settings = Settings()
    metrobus_gtfs_static.run(settings)


@cli.command()
def ingest_metrobus_gtfs_email() -> None:
    """Refresh JWT, trigger sinopticoplus email delivery, parse attachments, land in GCS."""
    settings = Settings()
    metrobus_gtfs_email.run(settings)


@cli.command()
def serve_metrobus_inbound() -> None:
    """Run the SendGrid inbound parse webhook server on :8080."""
    metrobus_inbound_webhook.serve()


@cli.command()
def run_metrobus_gtfs_rt_daemon() -> None:
    """Poll GTFS-RT vehicle positions every N seconds and land protobuf snapshots in GCS."""
    settings = Settings()
    metrobus_gtfs_rt.run(settings)


@cli.command()
def ingest_weather() -> None:
    """Fetch Open-Meteo hourly weather for 5 CDMX coordinates and land in GCS."""
    settings = Settings()
    weather_openmeteo.run(settings)


if __name__ == "__main__":
    cli()
