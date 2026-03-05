# FlowLens Makefile
# Usage: make <target>
# Requires: docker, gcloud, terraform (>=1.7), jq, curl

SHELL := /bin/bash
.PHONY: dev build deploy logs latency demo test clean

# Load .env if present
-include .env
export

GCP_PROJECT   ?= $(GCP_PROJECT_ID)
GCP_REGION    ?= us-central1
IMAGE_TAG     ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo "latest")
REGISTRY      := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/flowlens/backend
CLOUD_RUN_SVC := flowlens-backend

# ─────────────────────────────────────────────────────────────────────────────
# LOCAL DEVELOPMENT
# ─────────────────────────────────────────────────────────────────────────────

## Start local backend + redis via docker-compose
dev:
	@echo "→ Starting FlowLens local stack..."
	docker compose up --build

## Run backend directly (no Docker) — faster iteration
dev-local:
	@echo "→ Starting backend locally (requires Redis on localhost:6379)..."
	cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

## Start Electron + Vite dev server
dev-frontend:
	@echo "→ Starting frontend dev server..."
	cd frontend && npm run dev

## Run backend tests
test:
	@echo "→ Running backend tests..."
	cd backend && python -m pytest tests/ -v --tb=short

# ─────────────────────────────────────────────────────────────────────────────
# DOCKER BUILD & PUSH
# ─────────────────────────────────────────────────────────────────────────────

## Build Docker image and push to Artifact Registry
build:
	@echo "→ Building image: $(REGISTRY):$(IMAGE_TAG)"
	gcloud auth configure-docker $(GCP_REGION)-docker.pkg.dev --quiet
	docker build \
		--platform linux/amd64 \
		--tag $(REGISTRY):$(IMAGE_TAG) \
		--tag $(REGISTRY):latest \
		./backend
	docker push $(REGISTRY):$(IMAGE_TAG)
	docker push $(REGISTRY):latest
	@echo "✅ Image pushed: $(REGISTRY):$(IMAGE_TAG)"

# ─────────────────────────────────────────────────────────────────────────────
# GCP DEPLOYMENT (Terraform)
# ─────────────────────────────────────────────────────────────────────────────

## Full deploy: build + push + terraform apply
deploy: build
	@echo "→ Deploying via Terraform..."
	cd infra/terraform && terraform init -upgrade
	cd infra/terraform && terraform apply \
		-auto-approve \
		-var="project_id=$(GCP_PROJECT)" \
		-var="region=$(GCP_REGION)" \
		-var="gemini_api_key=$(GEMINI_API_KEY)" \
		-var="image_tag=$(IMAGE_TAG)"
	@echo "✅ Deployment complete."
	@$(MAKE) latency

## Terraform plan (dry run)
plan:
	cd infra/terraform && terraform init -upgrade
	cd infra/terraform && terraform plan \
		-var="project_id=$(GCP_PROJECT)" \
		-var="region=$(GCP_REGION)" \
		-var="gemini_api_key=REDACTED" \
		-var="image_tag=$(IMAGE_TAG)"

## Destroy all GCP resources (careful!)
destroy:
	@echo "⚠️  This will DESTROY all FlowLens GCP resources."
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	cd infra/terraform && terraform destroy \
		-var="project_id=$(GCP_PROJECT)" \
		-var="region=$(GCP_REGION)" \
		-var="gemini_api_key=REDACTED" \
		-auto-approve

# ─────────────────────────────────────────────────────────────────────────────
# OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

## Tail Cloud Run logs
logs:
	gcloud run services logs tail $(CLOUD_RUN_SVC) --region=$(GCP_REGION) --project=$(GCP_PROJECT)

## Fetch and display p50/p95 latency stats from /health endpoint
latency:
	@echo "→ Fetching latency stats from $(CLOUD_RUN_URL)/health ..."
	@curl -s "$(CLOUD_RUN_URL)/health" | jq '{status, p50_latency_ms, p95_latency_ms, total_sessions}'

## Open live demo endpoint in default browser
demo:
	@echo "→ Opening demo endpoint..."
	@xdg-open "$(CLOUD_RUN_URL)/demo" 2>/dev/null || open "$(CLOUD_RUN_URL)/demo" 2>/dev/null || \
		echo "Open manually: $(CLOUD_RUN_URL)/demo"

# ─────────────────────────────────────────────────────────────────────────────
# SUBMISSION
# ─────────────────────────────────────────────────────────────────────────────

## Run submission completeness checker
check:
	python scripts/submission_check.py

## Tag and push release version
release:
	git tag v1.0.0
	git push origin v1.0.0
	@echo "✅ Tagged v1.0.0"

## Clean local build artifacts
clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf frontend/dist frontend/dist-electron
