# infra/backend.tf

## What it does

Configures the Terraform backend (remote state storage) and declares version constraints for Terraform and the Google provider.

- **Backend:** Remote state stored in GCS bucket `cdmx-mobility-tfstate` under the prefix `terraform/state`. Using GCS means state is shared across machines and CI/CD — no local `terraform.tfstate` files are committed.
- **Terraform version:** `~> 1.9.5` (patch-level compatible with 1.9.5).
- **Google provider:** `hashicorp/google ~> 6.5.0`.

## How it ties with the rest of the project

- **[infra/providers.tf](providers.tf)** — Configures the `google` provider declared here with project and region values.
- **[.github/workflows/ci.yml](../.github/workflows/ci.yml)** — The `terraform-validate` CI job runs `terraform init -backend=false` (skips backend connection) followed by `terraform validate`. A real `terraform plan/apply` requires GCS access.
- **[Makefile](../Makefile)** — `make tf-init` runs `terraform init`, which reads this file to connect to the GCS backend.
- The `cdmx-mobility-tfstate` bucket must be created manually before the first `terraform init` (it cannot be provisioned by the same Terraform config it stores state for).
