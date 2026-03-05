terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ───────────────────────────────────────────────────────────────────────────
# Enable required APIs
# ───────────────────────────────────────────────────────────────────────────

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudlogging.googleapis.com",
    "vpcaccess.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ───────────────────────────────────────────────────────────────────────────
# Artifact Registry — Docker image repository
# ───────────────────────────────────────────────────────────────────────────

resource "google_artifact_registry_repository" "flowlens" {
  depends_on    = [google_project_service.apis]
  location      = var.region
  repository_id = "flowlens"
  format        = "DOCKER"
  description   = "FlowLens backend container images"
}

# ───────────────────────────────────────────────────────────────────────────
# Secret Manager — Gemini API key
# ───────────────────────────────────────────────────────────────────────────

resource "google_secret_manager_secret" "gemini_api_key" {
  depends_on = [google_project_service.apis]
  secret_id  = "GEMINI_API_KEY"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "gemini_api_key_v1" {
  secret      = google_secret_manager_secret.gemini_api_key.id
  secret_data = var.gemini_api_key
}

# ───────────────────────────────────────────────────────────────────────────
# Service Account for Cloud Run
# ───────────────────────────────────────────────────────────────────────────

resource "google_service_account" "cloudrun_sa" {
  account_id   = "flowlens-backend-sa"
  display_name = "FlowLens Cloud Run Service Account"
}

resource "google_secret_manager_secret_iam_member" "cloudrun_secret_access" {
  secret_id = google_secret_manager_secret.gemini_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudrun_sa.email}"
}

# Logging writer
resource "google_project_iam_member" "cloudrun_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloudrun_sa.email}"
}

# ───────────────────────────────────────────────────────────────────────────
# VPC connector (for Cloud Run → Redis private access)
# ───────────────────────────────────────────────────────────────────────────

resource "google_compute_network" "flowlens_vpc" {
  name                    = "flowlens-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "flowlens_subnet" {
  name          = "flowlens-subnet"
  ip_cidr_range = "10.8.0.0/28"
  region        = var.region
  network       = google_compute_network.flowlens_vpc.id
}

resource "google_vpc_access_connector" "connector" {
  depends_on    = [google_project_service.apis]
  name          = "flowlens-vpc-connector"
  region        = var.region
  subnet {
    name = google_compute_subnetwork.flowlens_subnet.name
  }
  machine_type = "e2-standard-4"
  min_instances = 2
  max_instances = 3
}

# ───────────────────────────────────────────────────────────────────────────
# Redis (Memorystore) — conversation state
# ───────────────────────────────────────────────────────────────────────────

resource "google_redis_instance" "flowlens_memory" {
  depends_on     = [google_project_service.apis]
  name           = "flowlens-memory"
  tier           = "BASIC"
  memory_size_gb = 1
  region         = var.region

  authorized_network = google_compute_network.flowlens_vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"

  redis_version     = "REDIS_7_0"
  display_name      = "FlowLens Conversation Memory"
}

# ───────────────────────────────────────────────────────────────────────────
# Cloud Run — backend service
# ───────────────────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "flowlens_backend" {
  depends_on = [
    google_project_service.apis,
    google_artifact_registry_repository.flowlens,
  ]

  name     = "flowlens-backend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloudrun_sa.email

    scaling {
      min_instance_count = 1   # Critical: avoids cold start during demo
      max_instance_count = 10
    }

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    timeout = "30s"

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/flowlens/backend:${var.image_tag}"

      resources {
        limits = {
          memory = "2Gi"
          cpu    = "2"
        }
        cpu_idle = false
      }

      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.flowlens_memory.host}:${google_redis_instance.flowlens_memory.port}/0"
      }

      env {
        name  = "PORT"
        value = "8000"
      }

      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }

      ports {
        container_port = 8000
      }
    }
  }
}

# Allow unauthenticated access (demo needs public URL)
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.flowlens_backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
