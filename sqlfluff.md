# .sqlfluff

## What it does

Configures [SQLFluff](https://sqlfluff.com/), the SQL linter used to enforce style consistency across all dbt models in `dbt_bigquery/models/`. It sets the SQL dialect to BigQuery, enables Jinja templating support for dbt macros, and excludes rules that conflict with the project's deliberate aligned-column formatting style.

## Key settings

| Setting | Value | Reason |
|---|---|---|
| `dialect` | `bigquery` | All SQL targets BigQuery |
| `templater` | `jinja` | dbt models use `{{ ref() }}`, `{{ source() }}`, `{{ config() }}` macros |
| `max_line_length` | `100` | Matches `ruff` and `black` line length in [pyproject.toml](pyproject.toml) |
| `exclude_rules` | `LT01, LT02, LT05, LT13, ST06, ST07, RF04` | See below |

## Excluded rules

The project uses **aligned-column formatting** (extra spaces before `as` to vertically align column names). This conflicts with several default SQLFluff rules:

- `LT01` / `LT02` — whitespace around operators / indentation
- `LT05` — line length (some aligned columns exceed 100 chars in context)
- `LT13` — whitespace at start of file
- `ST06` / `ST07` — select wildcards / DISTINCT placement
- `RF04` — reserved keywords as identifiers

**Do not add `# noqa: sqlfluff` suppressions in SQL files.** If a new rule conflicts with project style, add it to `exclude_rules` here instead.

## How it ties with the rest of the project

- **[dbt_bigquery/models/](dbt_bigquery/models/)** — All `.sql` files in this directory are subject to these lint rules.
- **[.pre-commit-config.yaml](.pre-commit-config.yaml)** — The `sqlfluff-lint` pre-commit hook uses this config file automatically (SQLFluff reads `.sqlfluff` from the repo root).
- **[Makefile](Makefile)** — `make lint` runs `uv run sqlfluff lint dbt_bigquery/models --dialect bigquery`.
- **[.github/workflows/ci.yml](.github/workflows/ci.yml)** — The `lint-and-test` job runs the same sqlfluff command in CI.
