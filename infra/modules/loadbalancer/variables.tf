variable "project_id" { type = string }
variable "region" { type = string }

variable "domain" {
  type        = string
  description = "Public domain for the dashboard (e.g. mobility.anuarhage.com)."
}

variable "dashboard_service_name" {
  type        = string
  description = "Name of the dashboard Cloud Run service."
}

variable "pipeline_api_service_name" {
  type        = string
  description = "Name of the pipeline-api Cloud Run service."
}
