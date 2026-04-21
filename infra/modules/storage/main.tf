variable "bucket_name" { type = string }
variable "location" { type = string }

resource "google_storage_bucket" "data" {
  name                        = var.bucket_name
  location                    = var.location
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age            = 90
      matches_prefix = ["raw/"]
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  lifecycle_rule {
    condition {
      age            = 7
      matches_prefix = ["staging/"]
    }
    action {
      type = "Delete"
    }
  }

  # GTFS-RT generates ~2,880 protobuf snapshots/day; move to Nearline after 30 days
  lifecycle_rule {
    condition {
      age            = 30
      matches_prefix = ["metrobus/vehicle_positions_raw/"]
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  # Silver Parquet is queried regularly for ~6 months, then infrequent
  lifecycle_rule {
    condition {
      age            = 180
      matches_prefix = ["silver/"]
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
}

# Create the zone "folders" by writing placeholder objects
resource "google_storage_bucket_object" "raw_placeholder" {
  name    = "raw/.keep"
  bucket  = google_storage_bucket.data.name
  content = " "
}

resource "google_storage_bucket_object" "staging_placeholder" {
  name    = "staging/.keep"
  bucket  = google_storage_bucket.data.name
  content = " "
}

resource "google_storage_bucket_object" "curated_placeholder" {
  name    = "curated/.keep"
  bucket  = google_storage_bucket.data.name
  content = " "
}

resource "google_storage_bucket_object" "silver_placeholder" {
  name    = "silver/.keep"
  bucket  = google_storage_bucket.data.name
  content = " "
}

output "bucket_name" {
  value = google_storage_bucket.data.name
}
