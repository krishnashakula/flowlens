output "cloud_run_url" {
  description = "Public URL of the FlowLens backend on Cloud Run"
  value       = google_cloud_run_v2_service.flowlens_backend.uri
}

output "artifact_registry_repo" {
  description = "Docker image repository path"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/flowlens"
}

output "redis_host" {
  description = "Redis host (private IP, accessible from Cloud Run via VPC)"
  value       = google_redis_instance.flowlens_memory.host
}

output "health_endpoint" {
  description = "Live health + latency stats URL (use for GCP proof in demo)"
  value       = "${google_cloud_run_v2_service.flowlens_backend.uri}/health"
}
