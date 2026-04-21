output "bucket_name" { value = module.storage.bucket_name }
output "bigquery_datasets" { value = module.bigquery.dataset_ids }
output "service_account_email" { value = module.iam.service_account_email }
output "wif_provider" { value = module.iam.wif_provider }
output "silver_gcs_prefix" { value = "gs://${module.storage.bucket_name}/silver/" }
