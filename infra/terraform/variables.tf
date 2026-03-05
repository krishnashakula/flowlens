variable "project_id" {
  description = "Google Cloud project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-central1"
}

variable "gemini_api_key" {
  description = "Gemini API key — stored in Secret Manager, never logged"
  type        = string
  sensitive   = true
}

variable "image_tag" {
  description = "Docker image tag to deploy (e.g. git SHA)"
  type        = string
  default     = "latest"
}
