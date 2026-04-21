variable "project_id" { type = string }
variable "location" { type = string }
variable "raw_bucket_name" { type = string }

locals {
  datasets = {
    raw_cdmx     = "Raw landing zone — external tables over GCS Parquet/JSON"
    staging_cdmx = "Staging — dbt staging models, type-cast and renamed"
    marts_cdmx   = "Marts — dimensional model, what Tableau queries"
    meta_cdmx    = "Pipeline metadata — ingestion logs, dbt run results, GE results"
  }
}

resource "google_bigquery_dataset" "datasets" {
  for_each    = local.datasets
  dataset_id  = each.key
  location    = var.location
  description = each.value

  default_table_expiration_ms = each.key == "staging_cdmx" ? 604800000 : null # 7 days for staging
  delete_contents_on_destroy  = false

  labels = {
    project = "cdmx-mobility"
    layer   = each.key
  }
}

resource "google_bigquery_table" "ecobici_station_status" {
  dataset_id          = google_bigquery_dataset.datasets["raw_cdmx"].dataset_id
  table_id            = "ecobici_station_status"
  project             = var.project_id
  deletion_protection = false

  external_data_configuration {
    source_format = "NEWLINE_DELIMITED_JSON"
    autodetect    = false
    source_uris   = ["gs://${var.raw_bucket_name}/ecobici/station_status/*"]

    hive_partitioning_options {
      mode              = "CUSTOM"
      source_uri_prefix = "gs://${var.raw_bucket_name}/ecobici/station_status/{ingestion_ts:STRING}"
    }
  }

  # BQ appends the Hive partition column to the schema automatically on first create.
  # mode = "NULLABLE" is required on every field — BQ API always returns it and the
  # provider compares schema as a JSON string, so omitting mode causes perpetual drift.
  schema = jsonencode([
    { name = "last_updated", type = "INTEGER", mode = "NULLABLE" },
    { name = "ttl", type = "INTEGER", mode = "NULLABLE" },
    { name = "data", type = "JSON", mode = "NULLABLE" },
    { name = "ingestion_ts", type = "STRING", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "ecobici_station_information" {
  dataset_id          = google_bigquery_dataset.datasets["raw_cdmx"].dataset_id
  table_id            = "ecobici_station_information"
  project             = var.project_id
  deletion_protection = false

  external_data_configuration {
    source_format = "NEWLINE_DELIMITED_JSON"
    autodetect    = false
    source_uris   = ["gs://${var.raw_bucket_name}/ecobici/station_information/*"]

    hive_partitioning_options {
      mode              = "CUSTOM"
      source_uri_prefix = "gs://${var.raw_bucket_name}/ecobici/station_information/{ingestion_date:DATE}"
    }
  }

  schema = jsonencode([
    { name = "last_updated", type = "INTEGER", mode = "NULLABLE" },
    { name = "ttl", type = "INTEGER", mode = "NULLABLE" },
    { name = "data", type = "JSON", mode = "NULLABLE" },
    { name = "ingestion_date", type = "DATE", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "ecobici_system_alerts" {
  dataset_id          = google_bigquery_dataset.datasets["raw_cdmx"].dataset_id
  table_id            = "ecobici_system_alerts"
  project             = var.project_id
  deletion_protection = false

  external_data_configuration {
    source_format = "NEWLINE_DELIMITED_JSON"
    autodetect    = false
    source_uris   = ["gs://${var.raw_bucket_name}/ecobici/system_alerts/*"]

    hive_partitioning_options {
      mode              = "CUSTOM"
      source_uri_prefix = "gs://${var.raw_bucket_name}/ecobici/system_alerts/{ingestion_ts:STRING}"
    }
  }

  schema = jsonencode([
    { name = "last_updated", type = "INTEGER", mode = "NULLABLE" },
    { name = "ttl", type = "INTEGER", mode = "NULLABLE" },
    { name = "data", type = "JSON", mode = "NULLABLE" },
    { name = "ingestion_ts", type = "STRING", mode = "NULLABLE" },
  ])
}

locals {
  # Schema for each GTFS static feed; all IDs/flags kept as STRING to avoid CSV type coercion.
  # Lat/lon columns use FLOAT (not FLOAT64) — BQ normalises FLOAT64 → FLOAT in its stored schema,
  # which would otherwise cause perpetual drift in terraform plan.
  # ingestion_date is the Hive partition column; BQ appends it automatically and we mirror it here.
  metrobus_static_schemas = {
    stops = jsonencode([
      { name = "stop_id", type = "STRING", mode = "NULLABLE" },
      { name = "stop_code", type = "STRING", mode = "NULLABLE" },
      { name = "stop_name", type = "STRING", mode = "NULLABLE" },
      { name = "stop_desc", type = "STRING", mode = "NULLABLE" },
      { name = "stop_lat", type = "FLOAT", mode = "NULLABLE" },
      { name = "stop_lon", type = "FLOAT", mode = "NULLABLE" },
      { name = "zone_id", type = "STRING", mode = "NULLABLE" },
      { name = "stop_url", type = "STRING", mode = "NULLABLE" },
      { name = "location_type", type = "INTEGER", mode = "NULLABLE" },
      { name = "parent_station", type = "STRING", mode = "NULLABLE" },
      { name = "stop_timezone", type = "STRING", mode = "NULLABLE" },
      { name = "wheelchair_boarding", type = "INTEGER", mode = "NULLABLE" },
      { name = "ingestion_date", type = "DATE", mode = "NULLABLE" },
    ])
    routes = jsonencode([
      { name = "route_id", type = "STRING", mode = "NULLABLE" },
      { name = "agency_id", type = "STRING", mode = "NULLABLE" },
      { name = "route_short_name", type = "STRING", mode = "NULLABLE" },
      { name = "route_long_name", type = "STRING", mode = "NULLABLE" },
      { name = "route_desc", type = "STRING", mode = "NULLABLE" },
      { name = "route_type", type = "INTEGER", mode = "NULLABLE" },
      { name = "route_url", type = "STRING", mode = "NULLABLE" },
      { name = "route_color", type = "STRING", mode = "NULLABLE" },
      { name = "route_text_color", type = "STRING", mode = "NULLABLE" },
      { name = "ingestion_date", type = "DATE", mode = "NULLABLE" },
    ])
    trips = jsonencode([
      { name = "route_id", type = "STRING", mode = "NULLABLE" },
      { name = "service_id", type = "STRING", mode = "NULLABLE" },
      { name = "trip_id", type = "STRING", mode = "NULLABLE" },
      { name = "trip_headsign", type = "STRING", mode = "NULLABLE" },
      { name = "trip_short_name", type = "STRING", mode = "NULLABLE" },
      { name = "direction_id", type = "INTEGER", mode = "NULLABLE" },
      { name = "block_id", type = "STRING", mode = "NULLABLE" },
      { name = "shape_id", type = "STRING", mode = "NULLABLE" },
      { name = "wheelchair_accessible", type = "INTEGER", mode = "NULLABLE" },
      { name = "bikes_allowed", type = "INTEGER", mode = "NULLABLE" },
      { name = "ingestion_date", type = "DATE", mode = "NULLABLE" },
    ])
    stop_times = jsonencode([
      { name = "trip_id", type = "STRING", mode = "NULLABLE" },
      { name = "arrival_time", type = "STRING", mode = "NULLABLE" }, # HH:MM:SS — can exceed 24:00:00 in GTFS
      { name = "departure_time", type = "STRING", mode = "NULLABLE" },
      { name = "stop_id", type = "STRING", mode = "NULLABLE" },
      { name = "stop_sequence", type = "INTEGER", mode = "NULLABLE" },
      { name = "stop_headsign", type = "STRING", mode = "NULLABLE" },
      { name = "pickup_type", type = "INTEGER", mode = "NULLABLE" },
      { name = "drop_off_type", type = "INTEGER", mode = "NULLABLE" },
      { name = "shape_dist_traveled", type = "FLOAT", mode = "NULLABLE" },
      { name = "timepoint", type = "INTEGER", mode = "NULLABLE" },
      { name = "ingestion_date", type = "DATE", mode = "NULLABLE" },
    ])
    calendar = jsonencode([
      { name = "service_id", type = "STRING", mode = "NULLABLE" },
      { name = "monday", type = "INTEGER", mode = "NULLABLE" },
      { name = "tuesday", type = "INTEGER", mode = "NULLABLE" },
      { name = "wednesday", type = "INTEGER", mode = "NULLABLE" },
      { name = "thursday", type = "INTEGER", mode = "NULLABLE" },
      { name = "friday", type = "INTEGER", mode = "NULLABLE" },
      { name = "saturday", type = "INTEGER", mode = "NULLABLE" },
      { name = "sunday", type = "INTEGER", mode = "NULLABLE" },
      { name = "start_date", type = "STRING", mode = "NULLABLE" },
      { name = "end_date", type = "STRING", mode = "NULLABLE" },
      { name = "ingestion_date", type = "DATE", mode = "NULLABLE" },
    ])
    shapes = jsonencode([
      { name = "shape_id", type = "STRING", mode = "NULLABLE" },
      { name = "shape_pt_lat", type = "FLOAT", mode = "NULLABLE" },
      { name = "shape_pt_lon", type = "FLOAT", mode = "NULLABLE" },
      { name = "shape_pt_sequence", type = "INTEGER", mode = "NULLABLE" },
      { name = "shape_dist_traveled", type = "FLOAT", mode = "NULLABLE" },
      { name = "ingestion_date", type = "DATE", mode = "NULLABLE" },
    ])
  }
}

resource "google_bigquery_table" "metrobus_static" {
  for_each            = local.metrobus_static_schemas
  dataset_id          = google_bigquery_dataset.datasets["raw_cdmx"].dataset_id
  table_id            = "metrobus_${each.key}"
  project             = var.project_id
  deletion_protection = false

  external_data_configuration {
    source_format = "CSV"
    autodetect    = false
    source_uris   = ["gs://${var.raw_bucket_name}/metrobus/static/${each.key}/*"]

    csv_options {
      quote             = "\""
      skip_leading_rows = 1
    }

    hive_partitioning_options {
      mode              = "CUSTOM"
      source_uri_prefix = "gs://${var.raw_bucket_name}/metrobus/static/${each.key}/{ingestion_date:DATE}"
    }
  }

  schema = each.value
}

resource "google_bigquery_table" "metrobus_vehicle_positions" {
  dataset_id          = google_bigquery_dataset.datasets["raw_cdmx"].dataset_id
  table_id            = "metrobus_vehicle_positions"
  project             = var.project_id
  deletion_protection = false

  external_data_configuration {
    source_format = "NEWLINE_DELIMITED_JSON"
    autodetect    = false
    source_uris   = ["gs://${var.raw_bucket_name}/metrobus/vehicle_positions/*"]

    hive_partitioning_options {
      mode              = "CUSTOM"
      source_uri_prefix = "gs://${var.raw_bucket_name}/metrobus/vehicle_positions/{ingestion_date:DATE}"
    }
  }

  schema = jsonencode([
    { name = "id", type = "STRING", mode = "NULLABLE", description = "GTFS-RT FeedEntity ID" },
    { name = "vehicle", type = "JSON", mode = "NULLABLE", description = "Full VehiclePosition proto serialised as JSON" },
    { name = "_snapshot_ts", type = "TIMESTAMP", mode = "NULLABLE", description = "UTC wall-clock time of the poll" },
    { name = "ingestion_date", type = "DATE", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "ingestion_log" {
  dataset_id          = google_bigquery_dataset.datasets["meta_cdmx"].dataset_id
  table_id            = "ingestion_log"
  project             = var.project_id
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "ingested_at"
  }

  schema = jsonencode([
    { name = "source", type = "STRING", mode = "REQUIRED" },
    { name = "run_id", type = "STRING", mode = "REQUIRED" },
    { name = "file_count", type = "INTEGER", mode = "NULLABLE" },
    { name = "byte_count", type = "INTEGER", mode = "NULLABLE" },
    { name = "row_count", type = "INTEGER", mode = "NULLABLE" },
    { name = "status", type = "STRING", mode = "REQUIRED" },
    { name = "error_message", type = "STRING", mode = "NULLABLE" },
    { name = "ingested_at", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

output "dataset_ids" {
  value = [for d in google_bigquery_dataset.datasets : d.dataset_id]
}
