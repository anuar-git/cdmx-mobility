variable "project_id" { type = string }
variable "bucket_name" { type = string }

resource "google_service_account" "pipeline" {
  account_id   = "cdmx-pipeline-sa"
  display_name = "CDMX Mobility Pipeline Service Account"
}

# Bucket-scoped permissions
resource "google_storage_bucket_iam_member" "pipeline_bucket" {
  bucket = var.bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

# BigQuery
resource "google_project_iam_member" "pipeline_bq_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "pipeline_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

# Dataproc
resource "google_project_iam_member" "pipeline_dataproc_worker" {
  project = var.project_id
  role    = "roles/dataproc.worker"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "pipeline_dataproc_editor" {
  project = var.project_id
  role    = "roles/dataproc.editor"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

# Secret Manager — read existing versions
resource "google_project_iam_member" "pipeline_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

# Secret Manager — write new versions (JWT rotation on each email ingest run)
resource "google_project_iam_member" "pipeline_secret_version_adder" {
  project = var.project_id
  role    = "roles/secretmanager.secretVersionAdder"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

# Secret Manager — list + destroy versions (needed to clean up old JWT versions after rotation)
resource "google_project_iam_member" "pipeline_secret_version_manager" {
  project = var.project_id
  role    = "roles/secretmanager.secretVersionManager"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

# Artifact Registry — allows CI to push Docker images
resource "google_project_iam_member" "pipeline_artifact_registry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

# Cloud Run — allows Cloud Scheduler to invoke Cloud Run Jobs via this SA
resource "google_project_iam_member" "pipeline_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

# Workload Identity Federation for GitHub Actions (no JSON keys!)
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Provider"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository == 'anuar-git/cdmx-mobility'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_impersonation" {
  service_account_id = google_service_account.pipeline.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/anuar-git/cdmx-mobility"
}

# Allow Cloud Scheduler to mint OAuth tokens for the pipeline SA when calling
# Dataproc and Cloud Run HTTP targets. Without this, every scheduler job that
# uses oauthToken with this SA returns HTTP 400 (token creation is denied).
resource "google_service_account_iam_member" "scheduler_token_creator" {
  service_account_id = google_service_account.pipeline.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
}

# Dataproc requires the API caller to have serviceAccountUser on the cluster SA.
# When the pipeline SA submits a workflow template whose cluster runs as itself,
# Dataproc checks that the caller can act as that SA — this self-binding satisfies it.
resource "google_service_account_iam_member" "pipeline_acts_as_self" {
  service_account_id = google_service_account.pipeline.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.pipeline.email}"
}

data "google_project" "project" {
  project_id = var.project_id
}

output "service_account_email" {
  value = google_service_account.pipeline.email
}

output "wif_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}
