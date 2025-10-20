# ReviewLens AI: Backend Code Samples

This file provides detailed code samples from the private backend repository for technical review. The full backend, including all Lambda source code and Terraform IaC, is in a private repository and is available upon request.

---

## Code Sample: `01-splitter-lambda/main.py`
*This function is triggered by S3, validates the input, performs idempotency checks, and orchestrates the entire parallel pipeline via Step Functions.*

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


## Code Sample: `find-job-lambda/main.py`

*This lightweight, .zip-packaged Lambda serves the API Gateway. It queries a DynamoDB Global Secondary Index (GSI) to decouple the frontend's upload_id from the backend's job_id, enabling a seamless UX.*

```python
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