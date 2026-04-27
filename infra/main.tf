module "storage" {
  source      = "./modules/storage"
  bucket_name = var.data_bucket_name
  location    = var.bq_location
}

module "bigquery" {
  source                = "./modules/bigquery"
  project_id            = var.project_id
  location              = var.bq_location
  raw_bucket_name       = module.storage.bucket_name
  metro_raw_bucket_name = var.metro_raw_bucket_name
}

module "iam" {
  source      = "./modules/iam"
  project_id  = var.project_id
  bucket_name = module.storage.bucket_name
}

module "dataproc" {
  source                = "./modules/dataproc"
  project_id            = var.project_id
  region                = var.region
  service_account_email = module.iam.service_account_email
  bucket_name           = module.storage.bucket_name
}

module "secrets" {
  source = "./modules/secrets"
}

module "cloudrun" {
  source                             = "./modules/cloudrun"
  project_id                         = var.project_id
  region                             = var.region
  service_account_email              = module.iam.service_account_email
  image                              = var.ingestor_image
  raw_bucket_name                    = module.storage.bucket_name
  gbfs_base_url                      = var.ecobici_gbfs_base_url
  metrobus_inbound_webhook_secret    = var.metrobus_inbound_webhook_secret
  metrobus_sinoptico_recipient_email = var.metrobus_sinoptico_recipient_email
}

module "scheduler" {
  source                   = "./modules/scheduler"
  project_id               = var.project_id
  region                   = var.region
  job_name                 = module.cloudrun.job_name
  metrobus_static_job_name = module.cloudrun.metrobus_static_job_name
  metrobus_email_job_name  = module.cloudrun.metrobus_email_job_name
  weather_ingest_job_name  = module.cloudrun.weather_ingest_job_name
  service_account_email    = module.iam.service_account_email

  # Staggered 30-min intervals so only one Dataproc cluster runs at a time.
  # CPUS_ALL_REGIONS quota is 10; each cluster uses 8 vCPUs (n1-standard-2 × 4 nodes).
  spark_workflow_schedules = {
    weather  = { template_id = module.dataproc.workflow_template_ids["weather"], schedule = "0 4 * * *" }
    metro    = { template_id = module.dataproc.workflow_template_ids["metro"], schedule = "0 6 * * *" }
    ecobici  = { template_id = module.dataproc.workflow_template_ids["ecobici"], schedule = "30 6 * * *" }
    metrobus = { template_id = module.dataproc.workflow_template_ids["metrobus"], schedule = "0 7 * * *" }
  }
}
