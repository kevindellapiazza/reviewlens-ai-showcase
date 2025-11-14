# --- Dead Letter Queue for failed AI processing batches ---
# This queue will store the input payloads of Lambda functions that fail permanently, allowing for later inspection and reprocessing.
resource "aws_sqs_queue" "ai_pipeline_dlq" {
  name = "${var.project_name}-ai-pipeline-dlq"
}