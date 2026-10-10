terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.95"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.17"
    }
  }

  # Partial configuration: supply bucket, key and region at init time.
  #   terraform init -backend-config=backend.hcl
  backend "s3" {}
}
