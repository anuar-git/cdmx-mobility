terraform {
  required_version = "~> 1.9.5"

  backend "gcs" {
    bucket = "cdmx-mobility-tfstate"
    prefix = "terraform/state"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.5.0"
    }
  }
}
