# --- 1. ECR Repositories for Lambdas ---
# Creates a dedicated ECR repository for each Lambda function's Docker image.
resource "aws_ecr_repository" "splitter_repo" {
  name = "${var.project_name}-01-splitter-repo"
}
resource "aws_ecr_repository" "sentiment_repo" {
  name = "${var.project_name}-02-sentiment-repo"
}
resource "aws_ecr_repository" "zeroshot_repo" {
  name = "${var.project_name}-03-zeroshot-repo"
}
resource "aws_ecr_repository" "absa_repo" {
  name = "${var.project_name}-04-absa-repo"
}
resource "aws_ecr_repository" "stitcher_repo" {
  name = "${var.project_name}-05-stitcher-repo"
}

# --- 2. ECR Image Data Sources (for Automated Updates) ---
# These data sources retrieve the latest pushed image for each repository.
# Using the image digest ensures that Lambda is only updated when a new image is actually pushed.
data "aws_ecr_image" "splitter_image" {
  repository_name = aws_ecr_repository.splitter_repo.name
  image_tag       = "latest"
}
data "aws_ecr_image" "sentiment_image" {
  repository_name = aws_ecr_repository.sentiment_repo.name
  image_tag       = "latest"
}
data "aws_ecr_image" "zeroshot_image" {
  repository_name = aws_ecr_repository.zeroshot_repo.name
  image_tag       = "latest"
}
data "aws_ecr_image" "absa_image" {
  repository_name = aws_ecr_repository.absa_repo.name
  image_tag       = "latest"
}
data "aws_ecr_image" "stitcher_image" {
  repository_name = aws_ecr_repository.stitcher_repo.name
  image_tag       = "latest"
}


# --- 3. IAM Roles and Policies ---
# Defines the trust relationship that allows AWS Lambda service to assume these roles.
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --- Role & Policy for Splitter Lambda ---
resource "aws_iam_role" "splitter_role" {
  name               = "${var.project_name}-01-splitter-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}
resource "aws_iam_policy" "splitter_policy" {
  name   = "${var.project_name}-01-splitter-permissions"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      { Action = "s3:GetObject", Effect = "Allow", Resource = ["${aws_s3_bucket.bronze_bucket.arn}/*"] },
      { Action = "s3:ListBucket", Effect = "Allow", Resource = ["${aws_s3_bucket.bronze_bucket.arn}"] },
      { Action = "states:StartExecution", Effect = "Allow", Resource = [aws_sfn_state_machine.processing_workflow.id] },
      { Action = "dynamodb:PutItem", Effect = "Allow", Resource = [aws_dynamodb_table.jobs_status_table.arn] }
    ]
  })
}
resource "aws_iam_role_policy_attachment" "splitter_attachments" {
  for_each = {
    basic_execution = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
    custom_policy   = aws_iam_policy.splitter_policy.arn
  }
  role       = aws_iam_role.splitter_role.name
  policy_arn = each.value
}

# --- Role & Policy for Sentiment Lambda ---
resource "aws_iam_role" "sentiment_role" {
  name               = "${var.project_name}-02-sentiment-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}
resource "aws_iam_role_policy_attachment" "sentiment_basic" {
  role       = aws_iam_role.sentiment_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# --- Role & Policy for ZeroShot Lambda ---
resource "aws_iam_role" "zeroshot_role" {
  name               = "${var.project_name}-03-zeroshot-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}
resource "aws_iam_role_policy_attachment" "zeroshot_basic" {
  role       = aws_iam_role.zeroshot_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# --- Role & Policy for ABSA Lambda ---
resource "aws_iam_role" "absa_role" {
  name               = "${var.project_name}-04-absa-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}
resource "aws_iam_policy" "absa_policy" {
  name   = "${var.project_name}-04-absa-permissions"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      { Action = "s3:PutObject", Effect = "Allow", Resource = ["${aws_s3_bucket.silver_bucket.arn}/*"] },
      { Action = "dynamodb:UpdateItem", Effect = "Allow", Resource = [aws_dynamodb_table.jobs_status_table.arn] }
    ]
  })
}
resource "aws_iam_role_policy_attachment" "absa_attachments" {
  for_each = {
    basic_execution = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
    custom_policy   = aws_iam_policy.absa_policy.arn
  }
  role       = aws_iam_role.absa_role.name
  policy_arn = each.value
}

# --- Role & Policy for Stitcher Lambda ---
resource "aws_iam_role" "stitcher_role" {
  name               = "${var.project_name}-05-stitcher-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}
resource "aws_iam_policy" "stitcher_policy" {
  name   = "${var.project_name}-05-stitcher-permissions"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      { Action = ["s3:GetObject", "s3:DeleteObject"], Effect = "Allow", Resource = ["${aws_s3_bucket.silver_bucket.arn}/*"] },
      { Action = "s3:ListBucket", Effect = "Allow", Resource = [aws_s3_bucket.silver_bucket.arn, aws_s3_bucket.gold_bucket.arn] },
      { Action = "s3:PutObject", Effect = "Allow", Resource = ["${aws_s3_bucket.gold_bucket.arn}/*"] },
      { Action = "dynamodb:UpdateItem", Effect = "Allow", Resource = [aws_dynamodb_table.jobs_status_table.arn] }
    ]
  })
}
resource "aws_iam_role_policy_attachment" "stitcher_attachments" {
  for_each = {
    basic_execution = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
    custom_policy   = aws_iam_policy.stitcher_policy.arn
  }
  role       = aws_iam_role.stitcher_role.name
  policy_arn = each.value
}



# --- Role & Policy for Status Checker Lambda ---
resource "aws_iam_role" "status_checker_role" {
  name               = "${var.project_name}-api-status-checker-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}
resource "aws_iam_policy" "status_checker_policy" {
  name   = "${var.project_name}-api-status-checker-permissions"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Action   = "dynamodb:GetItem",
      Effect   = "Allow",
      Resource = [aws_dynamodb_table.jobs_status_table.arn]
    }]
  })
}
resource "aws_iam_role_policy_attachment" "status_checker_attachments" {
  for_each = {
    basic_execution = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
    custom_policy   = aws_iam_policy.status_checker_policy.arn
  }
  role       = aws_iam_role.status_checker_role.name
  policy_arn = each.value
}

# --- Role & Policy for Find-Job Lambda ---
resource "aws_iam_role" "find_job_role" {
  name               = "${var.project_name}-find-job-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_policy" "find_job_policy" {
  name   = "${var.project_name}-find-job-permissions"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Action   = "dynamodb:Query",
      Effect   = "Allow",
      Resource = "${aws_dynamodb_table.jobs_status_table.arn}/index/SourceFileIndex"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "find_job_attachments" {
  for_each = {
    basic_execution = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
    custom_policy   = aws_iam_policy.find_job_policy.arn
  }
  role       = aws_iam_role.find_job_role.name
  policy_arn = each.value
}



# --- Policy to allow sending messages to the Dead Letter Queue ---
# This policy is reused across all processing Lambdas that have a DLQ configured.
resource "aws_iam_policy" "dlq_writer_policy" {
  name   = "${var.project_name}-dlq-writer-policy"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Action   = "sqs:SendMessage",
      Effect   = "Allow",
      Resource = aws_sqs_queue.ai_pipeline_dlq.arn
    }]
  })
}

# --- Attach DLQ policy to the three processing roles ---
resource "aws_iam_role_policy_attachment" "sentiment_dlq_attachment" {
  role       = aws_iam_role.sentiment_role.name
  policy_arn = aws_iam_policy.dlq_writer_policy.arn
}

resource "aws_iam_role_policy_attachment" "zeroshot_dlq_attachment" {
  role       = aws_iam_role.zeroshot_role.name
  policy_arn = aws_iam_policy.dlq_writer_policy.arn
}

resource "aws_iam_role_policy_attachment" "absa_dlq_attachment" {
  role       = aws_iam_role.absa_role.name
  policy_arn = aws_iam_policy.dlq_writer_policy.arn
}


# --- 4. Lambda Functions ---
# Defines the configuration for each Lambda function.
resource "aws_lambda_function" "splitter_lambda" {
  function_name = "${var.project_name}-01-splitter-lambda"
  role          = aws_iam_role.splitter_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.splitter_repo.repository_url}@${data.aws_ecr_image.splitter_image.id}"
  timeout       = 600
  memory_size   = 2048
  # reserved_concurrent_executions = 1
  environment {
    variables = {
      STATE_MACHINE_ARN   = aws_sfn_state_machine.processing_workflow.id
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.jobs_status_table.name
      BATCH_SIZE          = "100"
    }
  }
}

resource "aws_lambda_function" "sentiment_lambda" {
  function_name = "${var.project_name}-02-sentiment-lambda"
  role          = aws_iam_role.sentiment_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.sentiment_repo.repository_url}@${data.aws_ecr_image.sentiment_image.id}"
  timeout       = 300
  memory_size   = 3008
  # reserved_concurrent_executions = 10
  environment {
    variables = {
      SENTIMENT_MODEL = "distilbert-base-uncased-finetuned-sst-2-english"
      HF_HOME            = "/var/task/model_cache"
    }
  }
  dead_letter_config {
    target_arn = aws_sqs_queue.ai_pipeline_dlq.arn
  }
}

resource "aws_lambda_function" "zeroshot_lambda" {
  function_name = "${var.project_name}-03-zeroshot-lambda"
  role          = aws_iam_role.zeroshot_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.zeroshot_repo.repository_url}@${data.aws_ecr_image.zeroshot_image.id}"
  timeout       = 300
  memory_size   = 3008
  # reserved_concurrent_executions = 10
  environment {
    variables = {
      ZEROSHOT_MODEL   = "typeform/distilbert-base-uncased-mnli"
      HF_HOME            = "/var/task/model_cache"
    }
  }
  dead_letter_config {
    target_arn = aws_sqs_queue.ai_pipeline_dlq.arn
  }
}

resource "aws_lambda_function" "absa_lambda" {
  function_name = "${var.project_name}-04-absa-lambda"
  role          = aws_iam_role.absa_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.absa_repo.repository_url}@${data.aws_ecr_image.absa_image.id}"
  timeout       = 900
  memory_size   = 3008

  environment {
    variables = {
      SILVER_BUCKET_NAME      = aws_s3_bucket.silver_bucket.bucket
      DYNAMODB_TABLE_NAME     = aws_dynamodb_table.jobs_status_table.name
      
      MODEL_DIR               = "/var/task/models/mDeBERTa-v3-base-mnli-xnli"
      SCORE_THRESHOLD         = "0.6"
      HF_HOME             = "/tmp/huggingface_cache"
    }
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.ai_pipeline_dlq.arn
  }
}

resource "aws_lambda_function" "stitcher_lambda" {
  function_name = "${var.project_name}-05-stitcher-lambda"
  role          = aws_iam_role.stitcher_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.stitcher_repo.repository_url}@${data.aws_ecr_image.stitcher_image.id}"
  timeout       = 900
  memory_size   = 3008
  # reserved_concurrent_executions = 1
  environment {
    variables = {
      SILVER_BUCKET_NAME  = aws_s3_bucket.silver_bucket.bucket
      GOLD_BUCKET_NAME    = aws_s3_bucket.gold_bucket.bucket
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.jobs_status_table.name
      BERTOPIC_LANGUAGE   = "english"
      NUMBA_CACHE_DIR     = "/tmp"
      HF_HOME             = "/tmp/huggingface_cache"
    }
  }
}

resource "aws_lambda_function" "status_checker_lambda" {
  function_name = "${var.project_name}-api-status-checker-lambda"
  role          = aws_iam_role.status_checker_role.arn
  handler       = "main.handler"
  runtime       = "python3.12"
  memory_size   = 128
  timeout       = 30
  # reserved_concurrent_executions = 1

  s3_bucket        = aws_s3_bucket.lambda_deployments_bucket.id
  s3_key           = aws_s3_object.status_checker_lambda_zip.key
  source_code_hash = filebase64sha256("../src/api-status-checker-lambda/deployment.zip")

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.jobs_status_table.name
    }
  }
}

resource "aws_lambda_function" "find_job_lambda" {
  function_name = "${var.project_name}-find-job-lambda"
  role          = aws_iam_role.find_job_role.arn
  handler       = "main.handler"
  runtime       = "python3.12"
  memory_size   = 128
  timeout       = 30
  # reserved_concurrent_executions = 1
  
  s3_bucket        = aws_s3_bucket.lambda_deployments_bucket.id
  s3_key           = aws_s3_object.find_job_lambda_zip.key
  source_code_hash = filebase64sha256("../src/find-job-lambda/deployment.zip")

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.jobs_status_table.name
      S3_BRONZE_BUCKET    = local.bronze_bucket_name
    }
  }
}


# --- 5. Lambda Triggers ---

# Trigger for S3 object creation to invoke the splitter Lambda.
resource "aws_s3_bucket_notification" "bronze_to_splitter_notification" {
  bucket = aws_s3_bucket.bronze_bucket.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.splitter_lambda.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
  }
  depends_on = [
    aws_lambda_permission.allow_s3_to_invoke_splitter,
    aws_lambda_function.splitter_lambda 
  ]
}

resource "aws_lambda_permission" "allow_s3_to_invoke_splitter" {
  statement_id  = "AllowS3InvokeSplitter"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.splitter_lambda.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.bronze_bucket.arn
}

# Permissions for API Gateway to invoke the API-facing Lambdas.
resource "aws_lambda_permission" "allow_api_gateway_to_invoke_status_checker" {
  statement_id  = "AllowAPIGatewayInvokeStatusChecker"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.status_checker_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "allow_api_gateway_to_invoke_stitcher" {
  statement_id  = "AllowAPIGatewayInvokeStitcher"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.stitcher_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "allow_api_gateway_to_invoke_find_job" {
  statement_id  = "AllowAPIGatewayInvokeFindJob"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.find_job_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main_api.execution_arn}/*/*"
}