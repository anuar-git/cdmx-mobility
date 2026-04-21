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
    # Propagate timezone to all Spark executor and driver processes
    echo "TZ=America/Mexico_City" >> /etc/environment
    source /etc/environment
    # Install packages absent from the Dataproc 2.2 base image.
    # h3 spatial indexing, GTFS-RT protobuf bindings, chispa test assertions.
    pip install --quiet h3==3.7.7 "gtfs-realtime-bindings" chispa
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
          zone                   = "${var.region}-a"
          service_account        = var.service_account_email
          service_account_scopes = ["cloud-platform"]
        }

        master_config {
          num_instances = 1
          machine_type  = "n1-standard-4"
          disk_config {
            boot_disk_type    = "pd-standard"
            boot_disk_size_gb = 50
          }
        }

        # 3 workers × n1-standard-4 → 12 vCPUs, 45 GB RAM total.
        # Ephemeral cost: ~$0.23/node/hr × 4 nodes × 0.33 hr ≈ $0.31 per run.
        worker_config {
          num_instances = 3
          machine_type  = "n1-standard-4"
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
      # conformance.zip is built and uploaded by CI in Step 9:
      #   cd spark_jobs && zip -r conformance.zip conformance/
      #   gsutil cp conformance.zip gs://${bucket}/code/spark_jobs/conformance.zip
      # Uncomment once the conformance package exists:
      # python_file_uris = ["gs://${var.bucket_name}/code/spark_jobs/conformance.zip"]
    }
  }
}

output "workflow_template_ids" {
  description = "Map of job key to Dataproc workflow template short name"
  value       = { for k, v in google_dataproc_workflow_template.spark_job : k => v.name }
}
