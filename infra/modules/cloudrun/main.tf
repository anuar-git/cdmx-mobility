variable "project_id" { type = string }
variable "region" { type = string }
variable "service_account_email" { type = string }
variable "image" { type = string }
variable "raw_bucket_name" { type = string }
variable "gbfs_base_url" { type = string }
variable "domain" {
  type        = string
  description = "Public domain for the dashboard (e.g. mobility.anuarhage.com). Used for CORS on the pipeline-api."
}

variable "metrobus_inbound_webhook_secret" {
  type      = string
  sensitive = true
}

variable "metrobus_sinoptico_recipient_email" {
  type = string
}

variable "pipeline_api_image" {
  type        = string
  description = "Full image URI for the pipeline health API container."
  default     = ""
}

variable "dashboard_image" {
  type        = string
  description = "Full image URI for the Next.js dashboard container."
  default     = ""
}

resource "google_artifact_registry_repository" "ingestor" {
  project       = var.project_id
  location      = var.region
  repository_id = "ingestor"
  format        = "DOCKER"
}

resource "google_cloud_run_v2_job" "ecobici_ingest" {
  name                = "ecobici-ingest"
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  template {
    template {
      service_account = var.service_account_email
      max_retries     = 0

      containers {
        image   = var.image
        command = ["uv", "run", "python", "main.py", "ingest-ecobici-gbfs"]

        env {
          name  = "CDMX_GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "CDMX_RAW_BUCKET_NAME"
          value = var.raw_bucket_name
        }

        env {
          name  = "CDMX_ECOBICI_GBFS_BASE_URL"
          value = var.gbfs_base_url
        }

        env {
          name  = "CDMX_ECOBICI_API_KEY"
          value = ""
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_job" "metrobus_gtfs_static" {
  name                = "metrobus-gtfs-static"
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  template {
    template {
      service_account = var.service_account_email
      max_retries     = 1

      containers {
        image   = var.image
        command = ["uv", "run", "python", "main.py", "ingest-metrobus-gtfs-static"]

        env {
          name  = "CDMX_GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "CDMX_RAW_BUCKET_NAME"
          value = var.raw_bucket_name
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }
    }
  }
}


resource "google_cloud_run_v2_job" "metrobus_gtfs_email" {
  name                = "metrobus-gtfs-email-ingest"
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  template {
    template {
      service_account = var.service_account_email
      max_retries     = 0

      containers {
        image   = var.image
        command = ["uv", "run", "python", "main.py", "ingest-metrobus-gtfs-email"]

        env {
          name  = "CDMX_GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "CDMX_RAW_BUCKET_NAME"
          value = var.raw_bucket_name
        }

        env {
          name  = "CDMX_METROBUS_SINOPTICO_RECIPIENT_EMAIL"
          value = var.metrobus_sinoptico_recipient_email
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service" "metrobus_gtfs_inbound" {
  name                = "metrobus-gtfs-inbound"
  location            = var.region
  project             = var.project_id
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = var.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image   = var.image
      command = ["uv", "run", "python", "main.py", "serve-metrobus-inbound"]

      env {
        name  = "CDMX_GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "CDMX_RAW_BUCKET_NAME"
        value = var.raw_bucket_name
      }

      env {
        name  = "CDMX_METROBUS_INBOUND_WEBHOOK_SECRET"
        value = var.metrobus_inbound_webhook_secret
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        # CPU throttled between requests — bills only for active request handling,
        # not idle time between the 5-minute sinopticoplus webhooks.
        cpu_idle = true
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 3
        timeout_seconds       = 3
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        period_seconds    = 30
        failure_threshold = 3
        timeout_seconds   = 5
      }
    }
  }
}

resource "google_cloud_run_v2_job" "weather_ingest" {
  name                = "weather-ingest"
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  template {
    template {
      service_account = var.service_account_email
      max_retries     = 1

      containers {
        image   = var.image
        command = ["uv", "run", "python", "main.py", "ingest-weather"]

        env {
          name  = "CDMX_GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "CDMX_RAW_BUCKET_NAME"
          value = var.raw_bucket_name
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "inbound_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.metrobus_gtfs_inbound.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}


# ── Pipeline API ──────────────────────────────────────────────────────────────
# Public read-only analytics API. Ingress locked to the load balancer so
# Cloud Armor rate-limiting is always enforced — the direct Cloud Run URL
# is unreachable from the internet.
resource "google_cloud_run_v2_service" "pipeline_api" {
  count               = var.pipeline_api_image != "" ? 1 : 0
  name                = "pipeline-api"
  location            = var.region
  project             = var.project_id
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = false

  template {
    service_account = var.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.pipeline_api_image

      env {
        name  = "CDMX_GCP_PROJECT_ID"
        value = var.project_id
      }

      # Same-origin in production (LB routes /api/* to this service).
      # localhost:3000 is kept for local dev.
      env {
        name  = "CORS_ORIGINS"
        value = "https://${var.domain},http://localhost:3000"
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "pipeline_api_public" {
  count    = var.pipeline_api_image != "" ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.pipeline_api[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}


# ── Dashboard ─────────────────────────────────────────────────────────────────
# Next.js standalone server. Ingress locked to the load balancer; Cloud Armor
# rate-limiting covers all dashboard traffic at the LB layer.
resource "google_cloud_run_v2_service" "dashboard" {
  count               = var.dashboard_image != "" ? 1 : 0
  name                = "dashboard"
  location            = var.region
  project             = var.project_id
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = false

  template {
    service_account = var.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.dashboard_image

      env {
        name  = "NODE_ENV"
        value = "production"
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "dashboard_public" {
  count    = var.dashboard_image != "" ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.dashboard[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}


# ── Outputs ───────────────────────────────────────────────────────────────────
output "pipeline_api_service_name" {
  value = length(google_cloud_run_v2_service.pipeline_api) > 0 ? google_cloud_run_v2_service.pipeline_api[0].name : ""
}

output "dashboard_service_name" {
  value = length(google_cloud_run_v2_service.dashboard) > 0 ? google_cloud_run_v2_service.dashboard[0].name : ""
}

output "job_name" {
  value = google_cloud_run_v2_job.ecobici_ingest.name
}

output "metrobus_static_job_name" {
  value = google_cloud_run_v2_job.metrobus_gtfs_static.name
}

output "metrobus_email_job_name" {
  value = google_cloud_run_v2_job.metrobus_gtfs_email.name
}

output "weather_ingest_job_name" {
  value = google_cloud_run_v2_job.weather_ingest.name
}

output "metrobus_inbound_url" {
  value = google_cloud_run_v2_service.metrobus_gtfs_inbound.uri
}

output "image_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.ingestor.repository_id}"
}
