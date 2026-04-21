variable "secrets" {
  type    = list(string)
  default = ["ecobici_api_key", "tableau_pat", "slack_webhook_url", "metro_cdmx_rss_url", "metrobus_sinoptico_jwt", "outlook_imap_app_password"]
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(var.secrets)
  secret_id = each.value

  replication {
    auto {}
  }
}
