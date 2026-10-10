.PHONY: help install lint test tf-validate manifests image

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Install app and dev dependencies
	pip install -r app/requirements-dev.txt

lint: ## Lint and format-check the app
	cd app && ruff check . && ruff format --check .

test: ## Run unit tests
	cd app && pytest -q

tf-validate: ## Format-check and validate Terraform (no AWS credentials needed)
	terraform -chdir=terraform fmt -check -recursive
	terraform -chdir=terraform init -backend=false -input=false
	terraform -chdir=terraform validate

manifests: ## Render and validate Kubernetes manifests
	kubectl kustomize k8s | kubeconform -strict -summary

image: ## Build the analyzer image locally
	docker build -t aiops/analyzer:dev app
