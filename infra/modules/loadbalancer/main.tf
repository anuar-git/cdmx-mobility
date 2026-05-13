# ── Static IP ─────────────────────────────────────────────────────────────────
resource "google_compute_global_address" "default" {
  name    = "cdmx-mobility-lb-ip"
  project = var.project_id
}

# ── Managed SSL certificate ───────────────────────────────────────────────────
resource "google_compute_managed_ssl_certificate" "default" {
  name    = "cdmx-mobility-ssl"
  project = var.project_id

  managed {
    domains = [var.domain]
  }
}

# ── Cloud Armor — rate limit 60 req/min per IP ────────────────────────────────
resource "google_compute_security_policy" "default" {
  name    = "cdmx-mobility-armor"
  project = var.project_id

  rule {
    action      = "throttle"
    priority    = 1000
    description = "60 req/min per IP"

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }

    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      rate_limit_threshold {
        count        = 60
        interval_sec = 60
      }
    }
  }

  rule {
    action      = "allow"
    priority    = 2147483647
    description = "Default allow"

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}

# ── Serverless NEGs ───────────────────────────────────────────────────────────
resource "google_compute_region_network_endpoint_group" "dashboard" {
  name                  = "cdmx-neg-dashboard"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  project               = var.project_id

  cloud_run {
    service = var.dashboard_service_name
  }
}

resource "google_compute_region_network_endpoint_group" "pipeline_api" {
  name                  = "cdmx-neg-pipeline-api"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  project               = var.project_id

  cloud_run {
    service = var.pipeline_api_service_name
  }
}

# ── Backend services ──────────────────────────────────────────────────────────
resource "google_compute_backend_service" "dashboard" {
  name                  = "cdmx-backend-dashboard"
  project               = var.project_id
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.default.id

  backend {
    group = google_compute_region_network_endpoint_group.dashboard.id
  }
}

resource "google_compute_backend_service" "pipeline_api" {
  name                  = "cdmx-backend-pipeline-api"
  project               = var.project_id
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.default.id

  backend {
    group = google_compute_region_network_endpoint_group.pipeline_api.id
  }
}

# ── URL map — /api/* → pipeline-api, /* → dashboard ──────────────────────────
resource "google_compute_url_map" "default" {
  name            = "cdmx-mobility-url-map"
  project         = var.project_id
  default_service = google_compute_backend_service.dashboard.id

  host_rule {
    hosts        = [var.domain]
    path_matcher = "main"
  }

  path_matcher {
    name            = "main"
    default_service = google_compute_backend_service.dashboard.id

    path_rule {
      paths   = ["/api/*"]
      service = google_compute_backend_service.pipeline_api.id
    }
  }
}

# ── HTTP → HTTPS redirect ─────────────────────────────────────────────────────
resource "google_compute_url_map" "redirect" {
  name    = "cdmx-mobility-http-redirect"
  project = var.project_id

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

# ── Proxies ───────────────────────────────────────────────────────────────────
resource "google_compute_target_https_proxy" "default" {
  name             = "cdmx-mobility-https-proxy"
  project          = var.project_id
  url_map          = google_compute_url_map.default.id
  ssl_certificates = [google_compute_managed_ssl_certificate.default.id]
}

resource "google_compute_target_http_proxy" "redirect" {
  name    = "cdmx-mobility-http-redirect-proxy"
  project = var.project_id
  url_map = google_compute_url_map.redirect.id
}

# ── Forwarding rules ──────────────────────────────────────────────────────────
resource "google_compute_global_forwarding_rule" "https" {
  name                  = "cdmx-mobility-https"
  project               = var.project_id
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.default.address
  port_range            = "443"
  target                = google_compute_target_https_proxy.default.id
}

resource "google_compute_global_forwarding_rule" "http" {
  name                  = "cdmx-mobility-http"
  project               = var.project_id
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.default.address
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect.id
}
