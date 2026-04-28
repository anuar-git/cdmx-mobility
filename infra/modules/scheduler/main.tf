variable "project_id" { type = string }
variable "region" { type = string }
variable "job_name" { type = string }
variable "metrobus_static_job_name" { type = string }
variable "metrobus_email_job_name" { type = string }
variable "service_account_email" { type = string }

variable "weather_ingest_job_name" { type = string }

# spark_workflow_schedules removed: Airflow DAG (daily_mobility_pipeline) owns
# all Dataproc workflow template triggers. Cloud Scheduler only drives the
# continuous ingestors (EcoBici poll, Metrobús email/static, weather).

resource "google_cloud_scheduler_job" "ecobici_poll" {
  name      = "ecobici-gbfs-poll"
  project   = var.project_id
  region    = var.region
  schedule  = "*/10 * * * *"
  time_zone = "America/Mexico_City"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${var.job_name}:run"

    oauth_token {
      service_account_email = var.service_account_email
    }
  }

  retry_config {
    retry_count = 0
  }
}

resource "google_cloud_scheduler_job" "metrobus_gtfs_email" {
  name      = "metrobus-gtfs-email-poll"
  project   = var.project_id
  region    = var.region
  schedule  = "*/5 * * * *"
  time_zone = "America/Mexico_City"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${var.metrobus_email_job_name}:run"

    oauth_token {
      service_account_email = var.service_account_email
    }
  }

  retry_config {
    retry_count = 0
  }
}

resource "google_cloud_scheduler_job" "metrobus_gtfs_static" {
  name      = "metrobus-gtfs-static-daily"
  project   = var.project_id
  region    = var.region
  schedule  = "0 4 * * *" # 04:00 AM Mexico City time — after SEMOVI typically publishes updates
  time_zone = "America/Mexico_City"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${var.metrobus_static_job_name}:run"

    oauth_token {
      service_account_email = var.service_account_email
    }
  }

  retry_config {
    retry_count = 1
  }
}

resource "google_cloud_scheduler_job" "weather_ingest" {
  name      = "weather-openmeteo-daily"
  project   = var.project_id
  region    = var.region
  schedule  = "0 2 * * *" # 02:00 AM Mexico City — well after midnight so yesterday is complete
  time_zone = "America/Mexico_City"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${var.weather_ingest_job_name}:run"

    oauth_token {
      service_account_email = var.service_account_email
    }
  }

  retry_config {
    retry_count = 1
  }
}
