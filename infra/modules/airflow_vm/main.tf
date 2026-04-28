variable "project_id" { type = string }
variable "region" { type = string }
variable "zone" {
  type    = string
  default = "us-central1-a"
}
variable "repo_url" {
  type    = string
  default = "https://github.com/anuar-git/cdmx-mobility.git"
}

# ── Service Account ───────────────────────────────────────────────────────────

resource "google_service_account" "airflow" {
  account_id   = "cdmx-airflow-sa"
  display_name = "Airflow VM Service Account"
  project      = var.project_id
}

locals {
  airflow_roles = [
    "roles/run.invoker",                  # trigger Cloud Run jobs
    "roles/dataproc.editor",              # instantiate workflow templates
    "roles/dataproc.worker",              # cluster SA binding
    "roles/bigquery.dataEditor",          # dbt writes to marts_cdmx
    "roles/bigquery.jobUser",             # dbt query execution
    "roles/storage.objectAdmin",          # read Silver / write Airflow logs
    "roles/secretmanager.secretAccessor", # read Fernet key + Slack URL at boot
    "roles/iam.serviceAccountUser",       # submit Dataproc jobs as pipeline SA
  ]
}

resource "google_project_iam_member" "airflow" {
  for_each = toset(local.airflow_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.airflow.email}"
}

# ── Secret Manager Secrets ────────────────────────────────────────────────────

resource "google_secret_manager_secret" "airflow_fernet" {
  secret_id = "airflow-fernet-key"
  project   = var.project_id
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "airflow_db_password" {
  secret_id = "airflow-db-password"
  project   = var.project_id
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "slack_webhook_url" {
  secret_id = "airflow-slack-webhook-url"
  project   = var.project_id
  replication {
    auto {}
  }
}

# ── Networking ────────────────────────────────────────────────────────────────

resource "google_compute_address" "airflow" {
  name    = "cdmx-airflow-ip"
  project = var.project_id
  region  = var.region
}

# Allow IAP TCP tunnelling only — the Airflow webserver is never exposed on 0.0.0.0/0.
resource "google_compute_firewall" "airflow_iap" {
  name    = "allow-iap-to-airflow"
  network = "default"
  project = var.project_id

  source_ranges = ["35.235.240.0/20"]

  allow {
    protocol = "tcp"
    ports    = ["22", "8080"]
  }

  target_tags = ["airflow"]
}

# ── Compute Instance ──────────────────────────────────────────────────────────

resource "google_compute_instance" "airflow" {
  name         = "cdmx-airflow"
  machine_type = "e2-standard-2"
  zone         = var.zone
  project      = var.project_id

  tags = ["airflow"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 50
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"
    access_config {
      nat_ip = google_compute_address.airflow.address
    }
  }

  service_account {
    email  = google_service_account.airflow.email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  metadata = {
    REPO_URL       = var.repo_url
    startup-script = file("${path.module}/startup.sh")
  }

  # Prevent accidental replacement — changing machine_type requires allow_stopping.
  allow_stopping_for_update = true
}

# ── Outputs ───────────────────────────────────────────────────────────────────

output "airflow_sa_email" {
  description = "Email of the Airflow VM service account"
  value       = google_service_account.airflow.email
}

output "airflow_vm_ip" {
  description = "External IP of the Airflow VM (access via IAP tunnel, not directly)"
  value       = google_compute_address.airflow.address
}

output "airflow_vm_name" {
  description = "Name of the Airflow Compute Engine instance"
  value       = google_compute_instance.airflow.name
}
