variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "bq_location" {
  type    = string
  default = "US"
}

variable "data_bucket_name" {
  type    = string
  default = "cdmx-mobility-raw"
}

variable "ingestor_image" {
  type        = string
  description = "Container image URI for the ingestor Cloud Run Job"
  default     = ""
}

variable "ecobici_gbfs_base_url" {
  type        = string
  description = "EcoBici GBFS base URL (public GBFS feed root, no trailing slash)"
  default     = ""
}

variable "metrobus_gtfs_static_dataset_id" {
  type        = string
  description = "CKAN dataset slug for the SEMOVI unified CDMX GTFS static ZIP (datos.cdmx.gob.mx)"
  default     = "gtfs"
}

variable "metrobus_gtfs_rt_vehicle_positions_url" {
  type        = string
  description = "GTFS-RT vehicle positions protobuf endpoint URL; obtain from SEMOVI/Metrobús operations"
  default     = ""
}

variable "metrobus_inbound_webhook_secret" {
  type        = string
  sensitive   = true
  description = "Random token embedded in the SendGrid inbound webhook URL path"
}

variable "metrobus_sinoptico_recipient_email" {
  type        = string
  description = "Email address sinopticoplus will send GTFS data to (e.g. gtfs@inbound.anuarhage.com)"
  default     = ""
}
