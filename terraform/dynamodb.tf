# --- DynamoDB Table for Job Status Tracking ---
# This table acts as the "state machine" for our pipeline, tracking the progress of each processing job.
resource "aws_dynamodb_table" "jobs_status_table" {
  name         = "${var.project_name}-jobs-status"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }
  
  # Add this attribute for the GSI
  attribute {
    name = "source_file"
    type = "S"
  }

  # Add a Global Secondary Index (GSI) to query jobs by their source file path. Allows find-job-lambda to work efficiently.
  global_secondary_index {
    name            = "SourceFileIndex"
    hash_key        = "source_file"
    projection_type = "ALL"
  }
}