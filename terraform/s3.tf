# --- Data Layer Buckets ---
# This project uses a "Medallion Architecture" for data storage.

# Bronze Layer: For raw, unmodified data ingestion.
resource "aws_s3_bucket" "bronze_bucket" {
  bucket = local.bronze_bucket_name
}

# Silver Layer: For intermediate, cleaned, and enriched data (in batches).
resource "aws_s3_bucket" "silver_bucket" {
  bucket = local.silver_bucket_name
}

# Gold Layer: For the final, aggregated, business-ready data.
resource "aws_s3_bucket" "gold_bucket" {
  bucket = local.gold_bucket_name
}

# --- S3 Security: Block Public Access ---
# Explicitly block all public access to the buckets.

resource "aws_s3_bucket_public_access_block" "bronze_access_block" {
  bucket = aws_s3_bucket.bronze_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "silver_access_block" {
  bucket = aws_s3_bucket.silver_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "gold_access_block" {
  bucket = aws_s3_bucket.gold_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}


# --- S3 Lifecycle Policy for Silver Bucket ---
# Automatically cleans up intermediate batch files after 7 days to manage costs and data clutter.
resource "aws_s3_bucket_lifecycle_configuration" "silver_bucket_lifecycle" {
  bucket = aws_s3_bucket.silver_bucket.id

  rule {
    id     = "cleanup-processed-batches"
    status = "Enabled"

    # An empty filter applies the rule to all objects in the bucket.
    filter {}

    expiration {
      days = 7
    }
  }
}

# --- S3 Bucket for Lambda Deployment Artifacts ---
# This bucket acts as a central repository for .zip deployment packages.It decouples the application code from the infrastructure code.

resource "aws_s3_bucket" "lambda_deployments_bucket" {
  # We use a fixed name here, but you can also make it dynamic
  bucket = "reviewlens-lambda-deployments-bucket-kevin"
}

resource "aws_s3_bucket_public_access_block" "lambda_deployments_access_block" {
  bucket = aws_s3_bucket.lambda_deployments_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# This resource is used to upload the local .zip file to the S3 bucket.
resource "aws_s3_object" "find_job_lambda_zip" {
  bucket = aws_s3_bucket.lambda_deployments_bucket.id
  key    = "find-job-lambda/deployment.zip"
  source = "../src/find-job-lambda/deployment.zip"
  etag   = filemd5("../src/find-job-lambda/deployment.zip")
}

resource "aws_s3_object" "status_checker_lambda_zip" {
  bucket = aws_s3_bucket.lambda_deployments_bucket.id
  key    = "api-status-checker-lambda/deployment.zip"
  source = "../src/api-status-checker-lambda/deployment.zip"
  etag   = filemd5("../src/api-status-checker-lambda/deployment.zip")
}