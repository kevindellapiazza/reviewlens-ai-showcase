# --- Provider & Terraform Configuration ---

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

# Configures the AWS provider and sets the default region for all resources.
provider "aws" {
  region = var.aws_region
}

# --- Resource Naming ---
# To ensure bucket names are globally unique, we append a random suffix.
# This avoids errors during 'terraform apply' if someone else has used the same name.
resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
}

# Local variables to create consistent names for all resources.
locals {
  project_name      = var.project_name
  bucket_suffix     = var.use_random_suffix ? "-${random_string.suffix.result}" : ""
  bronze_bucket_name = "${local.project_name}-bronze-bucket${local.bucket_suffix}"
  silver_bucket_name = "${local.project_name}-silver-bucket${local.bucket_suffix}"
  gold_bucket_name   = "${local.project_name}-gold-bucket${local.bucket_suffix}"
}