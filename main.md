# main.py

## What it does

`main.py` is the top-level CLI entry point for the entire ingestion platform. It defines a Click command group with four sub-commands, each corresponding to one ingestion workflow:

| Command | Module called | Trigger |
|---|---|---|
| `ingest-metro-affluence` | `ingestion.metro.affluence.run()` | GitHub Actions CI (every push to `main`) |
| `ingest-ecobici-gbfs` | `ingestion.ecobici.gbfs.run()` | Cloud Run Job (Cloud Scheduler, every 2 min) |
| `ingest-metrobus-gtfs-static` | `ingestion.metrobus.gtfs_static.run()` | Cloud Run Job (Cloud Scheduler, daily 04:00) |
| `run-metrobus-gtfs-rt-daemon` | `ingestion.metrobus.gtfs_rt.run()` | Cloud Run Service (always-on) |

Each command instantiates `Settings` (which reads `CDMX_`-prefixed env vars) and passes it into the relevant `run()` function. No business logic lives here — it is purely a routing layer.

## Tools used

- **[click](https://click.palletsprojects.com/)** — CLI framework. `@click.group()` + `@cli.command()` create the sub-command structure.
- **[ingestion/config.py](ingestion/config.py)** — `Settings` pydantic-settings class; constructed once per command invocation.

## How it ties with the rest of the project

- **Docker** — [Dockerfile](Dockerfile) sets `ENTRYPOINT ["uv", "run", "python", "main.py"]`, so every container invocation goes through this file.
- **CI/CD** — [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs `uv run python main.py ingest-metro-affluence` and `uv run python main.py ingest-metrobus-gtfs-static` on every push to `main`.
- **Cloud Run** — The `ingest-ecobici-gbfs` and `run-metrobus-gtfs-rt-daemon` commands are the container entrypoints for Cloud Run resources defined in [`infra/modules/cloudrun/main.tf`](infra/modules/cloudrun/main.tf).
- **Makefile** — [`Makefile`](Makefile) `ingest-metro` and `ingest-ecobici` targets call into this CLI.
