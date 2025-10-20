# ReviewLens AI: Backend Code & Infrastructure Samples
This file provides detailed code samples from the private backend repository for technical review. The full backend, including all Lambda source code and Terraform IaC, is in a private repository and is available upon request.

## Part 1: Application Logic (Python Lambda Code)
Code Sample: `01-splitter-lambda/main.py`
This function is triggered by S3, validates the input, performs idempotency checks, and orchestrates the entire parallel pipeline via Step Functions.

```python
import os
import boto3
import pandas as pd
import json
from io import StringIO

# --- Environment Variables ---
STATE_MACHINE_ARN = os.environ['STATE_MACHINE_ARN']
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 200))

# --- AWS Clients ---
s3_client = boto3.client('s3')
stepfunctions_client = boto3.client('stepfunctions')
table = boto3.resource('dynamodb').Table(DYNAMODB_TABLE_NAME)

def handler(event, context):
    """
    This function is triggered by an S3 upload from the frontend. It is idempotent.
    1.  Uses the file's ETag as a deterministic job_id.
    2.  Reads the JSON column mapping from S3 object metadata.
    3.  Validates, standardizes, and combines title and text columns.
    4.  If it's a new job, it registers it in DynamoDB and starts the Step Functions workflow.
    """
    print("Splitter handler started...")
    job_id = None
    
    try:
        # --- 1. Get file and job identifiers ---
        record = event['Records'][0]['s3']
        bucket_name = record['bucket']['name']
        file_key = record['object']['key']
        job_id = record['object']['eTag'] # Use ETag for idempotency
        
        print(f"Processing file: s3://{bucket_name}/{file_key}")
        print(f"Using deterministic Job ID (ETag): {job_id}")

        # --- 2. Retrieve and validate metadata ---
        s3_object = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        metadata = s3_object.get('Metadata', {})
        column_mapping_str = metadata.get('mapping')
        
        if not column_mapping_str:
            raise ValueError("Metadata key 'mapping' is missing from S3 object.")
        
        column_mapping = json.loads(column_mapping_str)
        required_backend_column = 'full_review_text'
        
        if required_backend_column not in column_mapping:
            raise ValueError(f"Mapping for '{required_backend_column}' is missing.")
        
        rename_dict = {v: k for k, v in column_mapping.items()}

        # --- 3. Read and process the CSV ---
        csv_content = s3_object['Body'].read().decode('utf-8')
        full_df = pd.read_csv(StringIO(csv_content))
        
        user_columns = list(rename_dict.keys())
        if not all(col in full_df.columns for col in user_columns):
            raise ValueError(f"One or more mapped columns not found in the CSV. Expected: {user_columns}")
            
        mapped_df = full_df[user_columns].rename(columns=rename_dict)

        if 'title' in mapped_df.columns:
            print("Title column found, combining with review text.")
            mapped_df['title'] = mapped_df['title'].fillna('')
            mapped_df['full_review_text'] = mapped_df['title'] + ' ' + mapped_df['full_review_text']
        
        final_columns_to_pass = ['full_review_text'] 
        mapped_df = mapped_df[final_columns_to_pass]
        
        chunks_list = [mapped_df.iloc[i:i + BATCH_SIZE] for i in range(0, len(mapped_df), BATCH_SIZE)]
        
        # --- 4. Register the job in DynamoDB (idempotent check) ---
        table.put_item(
            Item={
                'job_id': job_id,
                'status': 'IN_PROGRESS',
                'total_batches': len(chunks_list),
                'processed_batches': 0,
                'source_file': f"s3://{bucket_name}/{file_key}"
            },
            ConditionExpression='attribute_not_exists(job_id)'
        )
        print(f"Job {job_id} successfully registered in DynamoDB.")

    except table.meta.client.exceptions.ConditionalCheckFailedException:
        print(f"Job {job_id} is a duplicate and was skipped.")
        return {'statusCode': 200, 'body': 'Duplicate job skipped.'}
    
    except Exception as e:
        print(f"A critical error occurred in the splitter: {e}")
        if job_id:
            table.put_item(Item={'job_id': job_id, 'status': 'SPLITTER_FAILED', 'error_message': str(e)})
        raise e

    # --- 5. Start the Step Functions executions ---
    for chunk in chunks_list:
        execution_input = { 'job_id': job_id, 'batch_data': chunk.to_json(orient='split') }
        stepfunctions_client.start_execution(stateMachineArn=STATE_MACHINE_ARN, input=json.dumps(execution_input))
    
    print(f"Successfully started {len(chunks_list)} executions for job {job_id}.")
    return {'statusCode': 200, 'body': f'Job {job_id} started.'}
```
---
Code Sample: `find-job-lambda/main.py`

This lightweight, .zip-packaged Lambda serves the API Gateway. It queries a DynamoDB Global Secondary Index (GSI) to decouple the frontend's upload_id from the backend's job_id, enabling a seamless UX.


```Python
import os
import json
import boto3
from boto3.dynamodb.conditions import Key

# --- Environment Variables ---
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
S3_BRONZE_BUCKET = os.environ['S3_BRONZE_BUCKET']

# --- AWS Clients ---
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

def handler(event, context):
    print(f"Find-job handler started with event: {event}")
    try:
        upload_id = event['pathParameters']['upload_id']
        
        # This path prefix is the exact value that the splitter-lambda saves.
        source_file_prefix = f"s3://{S3_BRONZE_BUCKET}/uploads/{upload_id}/"
        print(f"Querying for jobs with exact source_file prefix: {source_file_prefix}")

        response = table.query(
            IndexName='SourceFileIndex',
            KeyConditionExpression=Key('source_file').eq(source_file_prefix)
        )
        
        if response.get('Items'):
            job_item = response['Items'][0]
            print(f"Job found: {job_item}")
            return {'statusCode': 200, 'body': json.dumps(job_item)}
        else:
            print("Job not yet found. The client should retry.")
            return {'statusCode': 404, 'body': json.dumps({'error': 'Job not yet registered.'})}
            
    except Exception as e:
        print(f"An error occurred: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Internal server error.'})}
```

# Part 2: Infrastructure as Code (Terraform Samples)
The entire backend infrastructure is defined with Terraform. Below are the three most significant files that define the core architecture of the pipeline.

## 1. step_function.tf
This file defines the heart of the pipeline: the orchestration logic that connects the three AI models in sequence. It shows how data flows from one Lambda to the next and includes robust error handling (Retry and Catch) for each step.

```Terraform

# --- Step Functions ---

# --- IAM Role for the State Machine ---
resource "aws_iam_role" "step_functions_role" {
  name               = "${var.project_name}-workflow-execution-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = { Service = "states.amazonaws.com" }
    }]
  })
}

# --- IAM Policy to allow Step Functions to invoke our Lambdas ---
resource "aws_iam_policy" "step_functions_policy" {
  name   = "${var.project_name}-workflow-invoke-lambda-policy"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Action   = "lambda:InvokeFunction",
      Effect   = "Allow",
      Resource = [
        aws_lambda_function.sentiment_lambda.arn,
        aws_lambda_function.zeroshot_lambda.arn,
        aws_lambda_function.absa_lambda.arn
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "step_functions_policy_attachment" {
  role       = aws_iam_role.step_functions_role.name
  policy_arn = aws_iam_policy.step_functions_policy.arn
}

# --- The State Machine Definition ---
resource "aws_sfn_state_machine" "processing_workflow" {
  name     = "${var.project_name}-processing-workflow"
  role_arn = aws_iam_role.step_functions_role.arn

  definition = jsonencode({
    Comment = "Orchestrates the AI analysis of a single review batch.",
    StartAt = "SentimentAnalysis",
    States = {
      "SentimentAnalysis" : {
        Type     = "Task",
        Resource = "arn:aws:states:::lambda:invoke",
        Parameters = {
          "FunctionName" = aws_lambda_function.sentiment_lambda.function_name,
          "Payload.$"    = "$"
        },
        Retry : [{ "ErrorEquals" : ["States.ALL"], "IntervalSeconds" : 10, "MaxAttempts" : 3, "BackoffRate" : 1.5 }],
        Catch : [{ "ErrorEquals" : ["States.ALL"], "Next" : "MarkAsFailed" }],
        "Next" : "ZeroShotClassification"
      },
      "ZeroShotClassification" : {
        Type     = "Task",
        Resource = "arn:aws:states:::lambda:invoke",
        # 'ResultPath' is removed to ensure the full event is passed on.
        Parameters = {
          "FunctionName" = aws_lambda_function.zeroshot_lambda.function_name,
          "Payload.$"    = "$"
        },
        Retry : [{ "ErrorEquals" : ["States.ALL"], "IntervalSeconds" : 10, "MaxAttempts" : 3, "BackoffRate" : 1.5 }],
        Catch : [{ "ErrorEquals" : ["States.ALL"], "Next" : "MarkAsFailed" }],
        "Next" : "AspectBasedAnalysis"
      },
      "AspectBasedAnalysis" : {
        Type     = "Task",
        Resource = "arn:aws:states:::lambda:invoke",
        Parameters = {
          "FunctionName" = aws_lambda_function.absa_lambda.function_name,
          "Payload.$"    = "$"
        },
        Retry : [{ "ErrorEquals" : ["States.ALL"], "IntervalSeconds" : 10, "MaxAttempts" : 3, "BackoffRate" : 1.5 }],
        Catch : [{ "ErrorEquals" : ["States.ALL"], "Next" : "MarkAsFailed" }],
        "End" : true
      },
      "MarkAsFailed" : {
        "Type" : "Fail",
        "Cause" : "An AI analysis step failed after multiple retries."
      }
    }
  })
}
```

## 2. lambda.tf (Key Sections)
This file defines all 6 Lambda functions. The samples below highlight the Hybrid Deployment Strategy (Docker vs. Zip) and the environment variable fixes (HF_HOME) required to run complex AI models in a serverless environment.

```Terraform
# --- 1. Docker-based AI Lambda (Example: sentiment) ---
# This Lambda is deployed as a container to manage heavy dependencies (torch, transformers).
resource "aws_lambda_function" "sentiment_lambda" {
  function_name = "${var.project_name}-02-sentiment-lambda"
  role          = aws_iam_role.sentiment_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.sentiment_repo.repository_url}@${data.aws_ecr_image.sentiment_image.id}"
  timeout       = 300
  memory_size   = 2048
  environment {
    variables = {
      SENTIMENT_MODEL = "distilbert-base-uncased-finetuned-sst-2-english"
      # This fix is critical: it tells the Hugging Face library to use the
      # only writable directory in Lambda (/tmp) for its cache.
      HF_HOME         = "/tmp/huggingface_cache"
    }
  }
  dead_letter_config { target_arn = aws_sqs_queue.ai_pipeline_dlq.arn }
}

# --- 2. Zip-based API Lambda (Example: find-job) ---
# This lightweight Lambda is deployed via S3 .zip for maximum speed and minimum cost.
resource "aws_lambda_function" "find_job_lambda" {
  function_name    = "${var.project_name}-00-find-job-lambda"
  role             = aws_iam_role.find_job_role.arn
  handler          = "main.handler"
  runtime          = "python3.12"
  memory_size      = 128
  timeout          = 30
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

# --- 3. Robust S3 Trigger ---
# This trigger is configured to be robust, filtering on a prefix and
# explicitly depending on the Lambda's permissions to avoid race conditions.
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
```

## 3. dynamodb.tf
This file defines the state-tracking table. The key feature is the Global Secondary Index (GSI), which allows the find-job-lambda to efficiently look up a job_id using the source_file path.

```Terraform
resource "aws_dynamodb_table" "jobs_status_table" {
  name         = "${var.project_name}-jobs-status"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id" # The primary key is the ETag

  attribute {
    name = "job_id"
    type = "S"
  }
  
  attribute {
    name = "source_file"
    type = "S"
  }

  # --- Key Feature: GSI for UX ---
  # This GSI allows the frontend to find a job record using the 'upload_id'
  # (which is part of the 'source_file' path) instead of the ETag.
  global_secondary_index {
    name            = "SourceFileIndex"
    hash_key        = "source_file"
    projection_type = "ALL" # Copy all data for the frontend to read
  }
}
```