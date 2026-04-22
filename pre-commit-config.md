# .pre-commit-config.yaml

## What it does

Configures [pre-commit](https://pre-commit.com/) hooks that run automatically before every `git commit`. These hooks enforce code quality and prevent common mistakes (trailing whitespace, secrets in code, bad YAML) without requiring manual steps.

Run all hooks manually with:
```bash
pre-commit run --all-files
```

## Hooks

### `pre-commit/pre-commit-hooks` (v5.0.0)

| Hook | Purpose |
|---|---|
| `trailing-whitespace` | Strips trailing whitespace from all files |
| `end-of-file-fixer` | Ensures files end with a single newline |
| `check-yaml` | Validates YAML syntax |
| `check-added-large-files` | Blocks files >1 MB from being committed |
| `check-merge-conflict` | Detects unresolved merge conflict markers |
| `detect-private-key` | Prevents private keys from being committed |

### `astral-sh/ruff-pre-commit` (v0.6.9)

- **`ruff`** — Lints Python with `--fix` (auto-fixes safe violations).
- **`ruff-format`** — Formats Python (ruff's built-in formatter, similar to black).

### `psf/black` (v24.10.0)

- **`black`** — Opinionated Python formatter; enforces consistent style.

### `sqlfluff/sqlfluff` (v3.2.0)

- **`sqlfluff-lint`** — Lints `.sql` files in BigQuery dialect. Configured further by [`.sqlfluff`](.sqlfluff).

### `antonbabenko/pre-commit-terraform` (v1.96.1)

- **`terraform_fmt`** — Auto-formats Terraform files.
- **`terraform_validate`** — Validates Terraform configuration syntax.

### `gitleaks/gitleaks` (v8.21.0)

- **`gitleaks`** — Scans for hardcoded secrets, API keys, tokens, and credentials.

## How it ties with the rest of the project

- **[pyproject.toml](pyproject.toml)** — Defines `ruff` and `black` configuration (line length, rules) that these hooks use.
- **[.sqlfluff](.sqlfluff)** — Contains BigQuery dialect and exclusion rules applied by the sqlfluff hook.
- **[infra/](infra/)** — Terraform hooks validate all `.tf` files under this directory.
- **[Makefile](Makefile)** — `make install` runs `pre-commit install` to register hooks; `make lint` mirrors checks for CI.
- **[.github/workflows/ci.yml](.github/workflows/ci.yml)** — CI runs the same ruff, black, sqlfluff, and pytest checks (hooks are not re-run in CI — the CI jobs replicate them).
