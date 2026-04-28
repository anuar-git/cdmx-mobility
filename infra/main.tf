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
  # spark_workflow_schedules removed: Airflow (module.airflow_vm) owns Dataproc triggers.
}

module "airflow_vm" {
  source     = "./modules/airflow_vm"
  project_id = var.project_id
  region     = var.region
  zone       = "${var.region}-a"
  repo_url   = "https://github.com/anuar-git/cdmx-mobility.git"
}
