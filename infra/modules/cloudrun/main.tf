variable "project_id" { type = string }
variable "region" { type = string }
variable "service_account_email" { type = string }
variable "image" { type = string }
variable "raw_bucket_name" { type = string }
variable "gbfs_base_url" { type = string }

variable "metrobus_gtfs_static_dataset_id" {
  type    = string
  default = "gtfs"
}

variable "metrobus_gtfs_rt_vehicle_positions_url" {
  type    = string
  default = ""
}

variable "metrobus_inbound_webhook_secret" {
  type      = string
  sensitive = true
}

variable "metrobus_sinoptico_recipient_email" {
  type = string
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

        env {
          name  = "CDMX_METROBUS_GTFS_STATIC_DATASET_ID"
          value = var.metrobus_gtfs_static_dataset_id
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

resource "google_cloud_run_v2_service" "metrobus_gtfs_rt_daemon" {
  name                = "metrobus-gtfs-rt-daemon"
  location            = var.region
  project             = var.project_id
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false

  template {
    service_account                  = var.service_account_email
    max_instance_request_concurrency = 1

    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }

    containers {
      image   = var.image
      command = ["uv", "run", "python", "main.py", "run-metrobus-gtfs-rt-daemon"]

      env {
        name  = "CDMX_GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "CDMX_RAW_BUCKET_NAME"
        value = var.raw_bucket_name
      }

      env {
        name  = "CDMX_METROBUS_GTFS_RT_VEHICLE_POSITIONS_URL"
        value = var.metrobus_gtfs_rt_vehicle_positions_url
      }

      resources {
        limits = {
          cpu    = "0.5"
          memory = "256Mi"
        }
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

resource "google_cloud_run_v2_job" "metro_ingest" {
  name                = "metro-ingest"
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  template {
    template {
      service_account = var.service_account_email
      max_retries     = 1

      containers {
        image   = var.image
        command = ["uv", "run", "python", "main.py", "ingest-metro-affluence"]

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

resource "google_monitoring_alert_policy" "gtfs_rt_daemon_down" {
  project      = var.project_id
  display_name = "Metrobús GTFS-RT daemon — no healthy instances for 5 min"
  combiner     = "OR"

  conditions {
    display_name = "Active instance count below 1"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type=\"cloud_run_revision\"",
        "resource.label.service_name=\"${google_cloud_run_v2_service.metrobus_gtfs_rt_daemon.name}\"",
        "metric.type=\"run.googleapis.com/container/instance_count\"",
      ])
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      duration        = "300s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  # No notification channels configured here; add Slack/PagerDuty channels after Terraform apply
  notification_channels = []

  alert_strategy {
    auto_close = "604800s" # 7 days
  }
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

output "metro_ingest_job_name" {
  value = google_cloud_run_v2_job.metro_ingest.name
}

output "metrobus_inbound_url" {
  value = google_cloud_run_v2_service.metrobus_gtfs_inbound.uri
}

output "image_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.ingestor.repository_id}"
}
