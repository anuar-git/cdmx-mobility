variable "project_id" { type = string }
variable "region" { type = string }
variable "service_account_email" { type = string }
variable "bucket_name" { type = string }

locals {
  spark_jobs = {
    ecobici  = "gs://${var.bucket_name}/code/spark_jobs/bronze_to_silver_ecobici.py"
    metro    = "gs://${var.bucket_name}/code/spark_jobs/bronze_to_silver_metro_affluence.py"
    metrobus = "gs://${var.bucket_name}/code/spark_jobs/bronze_to_silver_metrobus_vehicles.py"
    weather  = "gs://${var.bucket_name}/code/spark_jobs/bronze_to_silver_weather.py"
  }
}

# Uploaded once; referenced by all four workflow templates via initialization_actions.
# Content is stable — Terraform only re-uploads if the content hash changes.
resource "google_storage_bucket_object" "dataproc_init" {
  name    = "code/dataproc/init.sh"
  bucket  = var.bucket_name
  content = <<-EOT
    #!/bin/bash
    set -euxo pipefail
    # Propagate timezone to Spark executor JVMs.
    echo "TZ=America/Mexico_City" >> /etc/environment
    source /etc/environment
    # Install packages absent from the Dataproc 2.2 base image.
    # google-cloud-{bigquery,storage} are pre-installed; do not re-add them here.
    pip install --quiet \
      structlog \
      click \
      pydantic-settings \
      h3==3.7.7 \
      "gtfs-realtime-bindings" \
      chispa
  EOT
}

resource "google_dataproc_workflow_template" "spark_job" {
  for_each    = local.spark_jobs
  name        = "cdmx-spark-${each.key}"
  location    = var.region
  dag_timeout = "3600s"

  placement {
    managed_cluster {
      cluster_name = "cdmx-spark-${each.key}-ephemeral"

      config {
        gce_cluster_config {
          # No zone — Dataproc Auto Zone picks the zone with available capacity.
          service_account        = var.service_account_email
          service_account_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        }

        master_config {
          num_instances = 1
          machine_type  = "e2-standard-2"
          disk_config {
            boot_disk_type    = "pd-standard"
            boot_disk_size_gb = 50
          }
        }

        # 3 workers × e2-standard-2 → 6 vCPUs; total cluster = 8 vCPUs.
        # Fits within the 10-vCPU CPUS_ALL_REGIONS project quota.
        # Ephemeral cost: ~$0.095/node/hr × 4 nodes × 0.5 hr ≈ $0.19 per run.
        worker_config {
          num_instances = 3
          machine_type  = "e2-standard-2"
          disk_config {
            boot_disk_type    = "pd-standard"
            boot_disk_size_gb = 50
          }
        }

        software_config {
          image_version = "2.2-debian12"
          properties = {
            "dataproc:dataproc.allow.zero.workers" = "false"
          }
        }

        initialization_actions {
          executable_file   = "gs://${var.bucket_name}/code/dataproc/init.sh"
          execution_timeout = "300s"
        }
      }
    }
  }

  jobs {
    step_id = "spark-job"
    pyspark_job {
      main_python_file_uri = each.value
      python_file_uris = [
        "gs://${var.bucket_name}/code/spark_jobs/spark_jobs.zip",
        "gs://${var.bucket_name}/code/spark_jobs/ingestion.zip",
      ]
      # {{INPUT_DATE}} is substituted at instantiation time via the parameters block below.
      # When empty the Spark job defaults to processing all available partitions.
      args = ["--gcp-project-id", var.project_id, "--input-date", "{{INPUT_DATE}}"]
    }
  }

  # INPUT_DATE lets Airflow (or a manual gcloud call) scope each run to a single
  # Bronze partition. Example:
  #   gcloud dataproc workflow-templates instantiate cdmx-spark-ecobici \
  #     --region=us-central1 --parameters=INPUT_DATE=2026-04-27
  # Leave empty to process all available dates (useful for first-time full loads).
  parameters {
    name        = "INPUT_DATE"
    description = "Bronze partition to process (YYYY-MM-DD). Empty = all partitions."
    fields      = ["jobs['spark-job'].pysparkJob.args[3]"]

    validation {
      regex {
        regexes = ["^(\\d{4}-\\d{2}-\\d{2})?$"]
      }
    }
  }
}

# Single-node cluster for the hourly EcoBici Silver refresh.
# 1 master + 0 workers = 1 IP, vs 4 IPs for the full daily template.
# This prevents IN_USE_ADDRESSES quota exhaustion when the daily pipeline
# Spark job overlaps with the hourly :05 trigger (VM=1 + daily=4 + hourly=1 = 6 ≤ 8).
resource "google_dataproc_workflow_template" "spark_ecobici_hourly" {
  name        = "cdmx-spark-ecobici-hourly"
  location    = var.region
  dag_timeout = "3600s"

  placement {
    managed_cluster {
      cluster_name = "cdmx-spark-ecobici-hourly-ephemeral"

      config {
        gce_cluster_config {
          service_account        = var.service_account_email
          service_account_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        }

        master_config {
          num_instances = 1
          machine_type  = "e2-standard-2"
          disk_config {
            boot_disk_type    = "pd-standard"
            boot_disk_size_gb = 50
          }
        }

        # Single-node mode: 0 workers, master handles all Spark tasks.
        # Uses only 1 IP vs 4 for the standard template, preventing quota
        # exhaustion when the daily pipeline cluster is still running.
        # Sufficient for one hour of incremental EcoBici data (~6-9 snapshots).
        software_config {
          image_version = "2.2-debian12"
          properties = {
            "dataproc:dataproc.allow.zero.workers" = "true"
          }
        }

        initialization_actions {
          executable_file   = "gs://${var.bucket_name}/code/dataproc/init.sh"
          execution_timeout = "300s"
        }
      }
    }
  }

  jobs {
    step_id = "spark-job"
    pyspark_job {
      main_python_file_uri = "gs://${var.bucket_name}/code/spark_jobs/bronze_to_silver_ecobici.py"
      python_file_uris = [
        "gs://${var.bucket_name}/code/spark_jobs/spark_jobs.zip",
        "gs://${var.bucket_name}/code/spark_jobs/ingestion.zip",
      ]
      args = ["--gcp-project-id", var.project_id, "--input-date", "{{INPUT_DATE}}"]
    }
  }

  parameters {
    name        = "INPUT_DATE"
    description = "Bronze partition to process (YYYY-MM-DD). Empty = all partitions."
    fields      = ["jobs['spark-job'].pysparkJob.args[3]"]

    validation {
      regex {
        regexes = ["^(\\d{4}-\\d{2}-\\d{2})?$"]
      }
    }
  }
}

output "workflow_template_ids" {
  description = "Map of job key to Dataproc workflow template short name"
  value       = { for k, v in google_dataproc_workflow_template.spark_job : k => v.name }
}
