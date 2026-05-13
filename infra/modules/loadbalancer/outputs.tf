output "lb_ip" {
  value       = google_compute_global_address.default.address
  description = "Static IP to point your DNS A record at."
}
