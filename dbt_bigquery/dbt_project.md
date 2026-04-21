# dbt_bigquery/dbt_project.yml

## What it does

The top-level dbt project configuration file. It defines how dbt builds models, which BigQuery datasets each model layer writes to, and the standard paths for each dbt artifact type.

## Model layers

| Layer | Directory | Materialization | BigQuery dataset |
|---|---|---|---|
| Staging | `models/staging/` | `view` | `staging_cdmx` |
| Intermediate | `models/intermediate/` | `ephemeral` | N/A (no physical table) |
| Marts | `models/marts/` | `table` | `marts_cdmx` |

- **Staging views** provide a clean, typed interface over raw external tables without duplicating data.
- **Ephemeral models** are inlined as CTEs — useful for intermediate transformations with no storage cost.
- **Mart tables** are the final analytics layer consumed by Tableau dashboards.

## Profile

Connects to BigQuery via `profile: 'cdmx_mobility'`. The profile is defined in `~/.dbt/profiles.yml` (not checked into the repo). The `dev` target writes to `*_dev` datasets to avoid polluting production data during development.

## Project name

`cdmx_mobility` — used as the top-level key in `models:` configuration and in dbt run output.

## How it ties with the rest of the project

- **[models/staging/sources.yml](models/staging/sources.yml)** — Declares the raw BigQuery external tables (sourced from GCS) that staging models read from.
- **[models/staging/](models/staging/)** — All `stg_*.sql` models; become views in `staging_cdmx`.
- **[models/marts/](models/marts/)** — All `mart_*.sql` models; become tables in `marts_cdmx`.
- **[infra/modules/bigquery/main.tf](../infra/modules/bigquery/main.tf)** — Provisions the `raw_cdmx`, `staging_cdmx`, `marts_cdmx`, and `meta_cdmx` BigQuery datasets that dbt writes to.
- **[Makefile](../Makefile)** — `make dbt-build` and `make dbt-test` run from inside this directory.
- **[.sqlfluff](../.sqlfluff)** — Lints the SQL files under `models/` using BigQuery dialect settings.
- **[.github/workflows/ci.yml](../.github/workflows/ci.yml)** — CI runs `sqlfluff lint dbt_bigquery/models` to validate all SQL models.
