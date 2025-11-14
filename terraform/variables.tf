# --- General Configuration Variables ---

variable "aws_region" {
  description = "The AWS region where resources will be created."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "The base name for all resources in this project."
  type        = string
  default     = "reviewlens"
}

variable "use_random_suffix" {
  description = "If true, appends a random suffix to S3 bucket names to ensure uniqueness."
  type        = bool
  default     = true
}