"""
ReviewLens AI: 01 - Splitter Lambda

This function is triggered by an S3 'put' event in the Bronze bucket.
It serves as the main orchestrator for the analysis pipeline.

Key Responsibilities:
1. Idempotency: Uses the file's ETag as a deterministic 'job_id' to
   prevent duplicate processing of the same file upload.
2. Metadata Parsing: Reads column mappings and dynamic AI labels
   (e.g., 'zero_shot_labels') from the S3 object's custom metadata.
3. Job Registration: Creates a job entry in DynamoDB with a 'IN_PROGRESS'
   status, using a ConditionExpression to enforce idempotency.
4. Data Splitting: Reads the uploaded CSV, applies column mappings,
   sanitizes text, and splits the DataFrame into smaller batches.
5. Fan-Out: Starts one AWS Step Function execution *for each batch*,
   passing the batch data and dynamic AI config to the state machine.
"""

import os
import boto3
import pandas as pd
import json
import re
from io import StringIO

# --- Environment Variables ---
# These are set by the Terraform configuration
STATE_MACHINE_ARN = os.environ['STATE_MACHINE_ARN']
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
# Use .get() for optional parameters, providing a robust default
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 100))

# --- Global Constants ---
# Default AI labels to use if none are provided in the S3 metadata.
# This makes the pipeline robust and backward-compatible.
DEFAULT_ZERO_SHOT_LABELS = "price,quality,shipping,customer service,fit,fabric"
DEFAULT_ABSA_LABELS = (
    "slow delivery,fast delivery,damaged box,good quality,poor quality,"
    "good fit,tight fit,good price,expensive"
)

# --- AWS Clients ---
# Initialize clients globally to leverage Lambda execution context reuse,
# improving performance by avoiding re-initialization on every invocation.
s3_client = boto3.client('s3')
stepfunctions_client = boto3.client('stepfunctions')
dynamodb_resource = boto3.resource('dynamodb')
table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)


def sanitize_text(text: str) -> str:
    """
    Cleans a single text string from problematic characters before AI analysis.

    This prevents downstream model failures from "poison pill" characters
    that can break tokenizers or other NLP libraries.

    Args:
        text: The raw input string.

    Returns:
        A sanitized string.
    """
    if not isinstance(text, str):
        return ""
    
    # Replace ampersand, which was identified as a "poison pill" for models
    text = text.replace('&', 'and')
    
    # Remove non-printable ASCII control characters
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    return text


def handler(event: dict, context: object) -> dict:
    """
    Main Lambda handler function triggered by S3.

    Args:
        event: The S3 event notification payload.
        context: The Lambda runtime context (unused).

    Returns:
        A dict with statusCode and body for API Gateway/Lambda responses.

    Raises:
        ValueError: If required 'mapping' metadata is missing or incomplete.
        Exception: Captures and logs any processing failure, updating
                   DynamoDB to 'SPLITTER_FAILED' for frontend visibility.
    """
    print("Splitter handler started...")
    job_id = None
    
    try:
        # --- 1. Get File and Job Identifiers ---
        record = event['Records'][0]['s3']
        bucket_name = record['bucket']['name']
        file_key = record['object']['key']
        
        # Use the S3 object's ETag as a deterministic, idempotent Job ID.
        # This guarantees that processing the same file upload twice
        # will result in a skipped job, not a duplicate analysis.
        job_id = record['object']['eTag']
        
        print(f"Processing file: s3://{bucket_name}/{file_key}")
        print(f"Using deterministic Job ID (ETag): {job_id}")

        # --- 2. Retrieve and Validate Metadata ---
        # The frontend attaches column mapping and dynamic AI labels
        # as custom 'Metadata' to the S3 object upon upload.
        s3_object = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        metadata = s3_object.get('Metadata', {})
        column_mapping_str = metadata.get('mapping') 
        
        if not column_mapping_str:
            raise ValueError("Metadata key 'mapping' is missing from S3 object.")
        
        # Deserialize the mapping string (sent as JSON)
        column_mapping = json.loads(column_mapping_str)
        
        # Get dynamic labels from metadata, falling back to global defaults
        dynamic_zero_shot_labels = column_mapping.get(
            'zero_shot_labels', DEFAULT_ZERO_SHOT_LABELS
        )
        dynamic_absa_labels = column_mapping.get(
            'absa_labels', DEFAULT_ABSA_LABELS
        )
        
        print(f"Using Zero-Shot labels: {dynamic_zero_shot_labels[:100]}...")
        print(f"Using ABSA labels: {dynamic_absa_labels[:100]}...")
        
        # Validate that the *required* backend column is present in the map
        required_backend_column = 'full_review_text'
        if required_backend_column not in column_mapping:
            raise ValueError(
                f"Mapping for '{required_backend_column}' is missing."
            )
        
        # Create the rename dict for pandas:
        # {'user_column_name': 'standard_backend_name', ...}
        # We only care about columns we actually use in the backend.
        valid_backend_cols = ['full_review_text', 'title', 'rating']
        rename_dict = {
            v: k for k, v in column_mapping.items() 
            if k in valid_backend_cols
        }

        # --- 3. Read and Process the CSV ---
        print("Reading and processing CSV content...")
        csv_content = s3_object['Body'].read().decode('utf-8')
        full_df = pd.read_csv(StringIO(csv_content))
        
        # Verify that all columns specified in the mapping *exist* in the CSV
        user_columns = list(rename_dict.keys())
        if not all(col in full_df.columns for col in user_columns):
            missing = [col for col in user_columns if col not in full_df.columns]
            raise ValueError(
                f"Mapped columns not found in CSV. Missing: {missing}"
            )
            
        # Select only the mapped columns and rename them to our standard
        mapped_df = full_df[user_columns].rename(columns=rename_dict)

        # If a 'title' column was provided, combine it with the review text
        if 'title' in mapped_df.columns:
            print("Title column found, combining with review text.")
            mapped_df['title'] = mapped_df['title'].fillna('')
            mapped_df['full_review_text'] = (
                mapped_df['title'] + ' ' + mapped_df['full_review_text']
            )
        else:
            print("No title column mapped, proceeding with review text only.")
        
        # Sanitize the final text column to prevent model errors
        mapped_df['full_review_text'] = mapped_df[
            'full_review_text'
        ].apply(sanitize_text)

        # Keep only the final, necessary columns for the AI pipeline
        final_columns = ['full_review_text']
        if 'rating' in mapped_df.columns:
            final_columns.append('rating')
        mapped_df = mapped_df[final_columns]
        
        # Split the DataFrame into a list of smaller DataFrames (batches)
        chunks_list = [
            mapped_df.iloc[i:i + BATCH_SIZE] 
            for i in range(0, len(mapped_df), BATCH_SIZE)
        ]
        total_batches = len(chunks_list)
        print(f"CSV split into {total_batches} batches of {BATCH_SIZE} rows.")

        # --- 4. Register the Job in DynamoDB (Idempotent Check) ---
        # 'source_file_prefix' is used by the 'find-job' API Lambda to
        # locate this job_id using the GSI.
        upload_dir = os.path.dirname(file_key)
        source_file_prefix = f"s3://{bucket_name}/{upload_dir}/"

        print(f"Registering job {job_id} in DynamoDB...")
        table.put_item(
            Item={
                'job_id': job_id,
                'status': 'IN_PROGRESS',
                'total_batches': total_batches,
                'processed_batches': 0,
                'source_file': source_file_prefix 
            },
            # This is the core of the idempotency logic.
            # If an item with this 'job_id' (ETag) already exists,
            # the put will fail with a ConditionalCheckFailedException.
            ConditionExpression='attribute_not_exists(job_id)'
        )
        print(f"Job {job_id} successfully registered.")

    except table.meta.client.exceptions.ConditionalCheckFailedException:
        # This is not an error, it's a successful idempotent skip.
        print(f"Job {job_id} is a duplicate (ETag already exists). Skipping.")
        return {'statusCode': 200, 'body': 'Duplicate job skipped.'}
    
    except Exception as e:
        # This is a *real* failure (e.g., bad CSV, missing mapping).
        print(f"[ERROR] A critical error occurred in the splitter: {e}")
        
        # If we have a job_id, log the failure to DynamoDB so the
        # frontend can see the 'SPLITTER_FAILED' status.
        if job_id:
            table.put_item(
                Item={
                    'job_id': job_id, 
                    'status': 'SPLITTER_FAILED', 
                    'error_message': str(e)
                }
            )
        # Re-raise the exception to fail the Lambda invocation
        raise e

    # --- 5. Start the Step Functions Executions ("Fan-Out") ---
    print(f"Starting {total_batches} Step Function executions...")
    for i, chunk in enumerate(chunks_list):
        # Pass the dynamic labels into the payload for EACH execution
        execution_input = { 
            'job_id': job_id, 
            # Send batch data as JSON string (Step Functions payload limit is 256KB)
            'batch_data': chunk.to_json(orient='split'),
            'config': {
                'zero_shot_labels': dynamic_zero_shot_labels,
                'absa_labels': dynamic_absa_labels
            },
            'batch_info': {
                'batch_index': i,
                'total_batches': total_batches
            }
        }
        
        # Start one parallel execution per batch
        stepfunctions_client.start_execution(
            stateMachineArn=STATE_MACHINE_ARN, 
            input=json.dumps(execution_input)
            # We don't need 'name' as SFN will generate a unique UUID
        )
    
    print(f"Successfully started all executions for job {job_id}.")
    return {'statusCode': 200, 'body': f'Job {job_id} started.'}