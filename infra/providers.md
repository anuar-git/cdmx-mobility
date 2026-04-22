# infra/providers.tf

## What it does

Configures the `google` Terraform provider with the project ID and region. Both values are sourced from input variables, making this configuration reusable across environments (dev, prod) simply by changing `terraform.tvars`.

```hcl
provider "google" {
  project = var.project_id
  region  = var.region
}
```

Authentication uses Application Default Credentials (ADC) — the provider picks up credentials from:
- `gcloud auth application-default login` (local development)
- Workload Identity Federation (GitHub Actions CI/CD)
- Service account attached to the compute resource (Cloud Run, Dataproc)

## How it ties with the rest of the project

- **[infra/backend.tf](backend.tf)** — Declares the `google` provider source (`hashicorp/google ~> 6.5.0`) and version constraint used here.
- **[infra/variables.tf](variables.tf)** — Defines `var.project_id` (`cdmx-mobility-prod`) and `var.region` (`us-central1`) consumed by this provider.
- **[infra/modules/iam/main.tf](modules/iam/main.tf)** — Provisions the Workload Identity Federation pool that GitHub Actions uses to authenticate as the provider's service account.
