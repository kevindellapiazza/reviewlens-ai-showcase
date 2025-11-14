"""
ReviewLens AI: 05 - Stitcher Lambda

This function is the final step of the pipeline, triggered by an
API Gateway POST request from the frontend.

Responsibilities:
1.  Updates the job status in DynamoDB to 'STITCHING'.
2.  Finds all processed batch files (.parquet) in the S3 Silver Bucket.
3.  Merges all batches into a single, complete DataFrame using awswrangler.
4.  Performs corpus-level Topic Modeling (BERTopic) on the 'full_review_text'
    to discover hidden themes.
5.  Saves the topic info (keywords, counts) to a separate
    '{job_id}_topics.parquet' file in the S3 Gold Bucket for the dashboard.
6.  Saves the final, fully-enriched DataFrame (with 'bertopic_id')
    to '{job_id}.parquet' in the S3 Gold Bucket.
7.  Deletes all temporary batch files from the S3 Silver Bucket.
8.  Updates the job status in DynamoDB to 'COMPLETED'.
"""

import os
import json
import awswrangler as wr
import boto3
import pandas as pd
from bertopic import BERTopic
from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS
from sentence_transformers import SentenceTransformer

# --- Environment Variables ---
SILVER_BUCKET_NAME = os.environ['SILVER_BUCKET_NAME']
GOLD_BUCKET_NAME = os.environ['GOLD_BUCKET_NAME']
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']

# This path MUST match the 'COPY' destination in the Dockerfile
LOCAL_MODEL_PATH = "/var/task/models/all-MiniLM-L6-v2"

# --- AWS Clients (Global Scope) ---
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

# --- Load Models ONCE (Lambda Cold Start / INIT Phase) ---
# This loads the "baked-in" models from the local filesystem
# for near-instant cold starts.
try:
    print(f"Loading embedding model from {LOCAL_MODEL_PATH}...")
    EMBEDDING_MODEL = SentenceTransformer(LOCAL_MODEL_PATH)
    print("Embedding model loaded successfully.")

    # Define the vectorizer, removing common English stop words
    STOP_WORDS = list(ENGLISH_STOP_WORDS)
    VECTORIZER = CountVectorizer(stop_words=STOP_WORDS)

    # Initialize the main BERTopic model
    BERTOPIC_MODEL = BERTopic(
        embedding_model=EMBEDDING_MODEL,
        vectorizer_model=VECTORIZER,
        verbose=False
    )
    print("BERTopic model initialized successfully.")
except Exception as e:
    print(f"FATAL: Failed to load models on cold start: {e}")
    raise e


def update_job_status(job_id: str, status: str, error_msg: str = None):
    """Helper function to update the job status in DynamoDB."""
    print(f"Updating job {job_id} status to: {status}")
    expr = "SET #st = :s"
    names = {'#st': 'status'}
    vals = {':s': status}
    
    if error_msg:
        expr += ", #err = :e"
        names['#err'] = 'error_message'
        vals[':e'] = error_msg
        
    table.update_item(
        Key={'job_id': job_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=vals
    )

def handler(event: dict, context: object) -> dict:
    """
    Main Lambda handler triggered by API Gateway (POST /stitch).

    Args:
        event: The API Gateway event payload, containing the 'job_id' in its body.
        context: The Lambda runtime context (unused).

    Returns:
        A standard API Gateway response dict (statusCode, headers, body).
    """
    print(f"Stitcher handler started...")
    job_id = None
    
    # --- 1. Parse job_id from API Gateway Body ---
    try:
        # Frontend sends {'job_id': '...'} in the POST request body
        body = json.loads(event.get('body', '{}'))
        job_id = body['job_id']
        if not job_id:
            raise KeyError
        print(f"Starting stitching process for job_id: {job_id}")
    except (KeyError, json.JSONDecodeError):
        print("[ERROR] Invalid request, 'job_id' is missing from body.")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': "Invalid request, 'job_id' is missing."})
        }

    # Define all S3 paths
    silver_path = f"s3://{SILVER_BUCKET_NAME}/processed-batches/{job_id}/"
    gold_path = f"s3://{GOLD_BUCKET_NAME}/{job_id}.parquet"
    topic_info_path = f"s3://{GOLD_BUCKET_NAME}/{job_id}_topics.parquet"

    try:
        # --- 2. Update status to "STITCHING" for frontend visibility ---
        update_job_status(job_id, 'STITCHING')
        
        # --- 3. Check if any successful batches exist ---
        if not wr.s3.list_objects(path=silver_path):
            print(f"No processed batches found for job {job_id}. Marking as FAILED.")
            update_job_status(job_id, 'FAILED_NO_BATCHES_COMPLETED')
            return {
                'statusCode': 200, # The API call itself succeeded
                'body': json.dumps({'message': 'Job failed: No batches were processed.'})
            }

        # --- 4. Read and merge all partial Parquet files ---
        print(f"Reading partial files from {silver_path}...")
        df_final = wr.s3.read_parquet(path=silver_path)
        print(f"Successfully merged {len(df_final)} total rows.")

        # --- 5. Perform Topic Modeling ---
        print(f"Starting Topic Modeling...")
        # Ensure we only process valid, non-empty strings
        docs = df_final['full_review_text'].dropna().astype(str).tolist()
        
        if docs:
            # This is the main ML compute step
            topics, _ = BERTOPIC_MODEL.fit_transform(docs)
            df_final['bertopic_id'] = topics
            print("Topic Modeling complete.")
            
            # --- 5b. Save separate Topic Info file for the dashboard ---
            print("Extracting topic info...")
            topic_info_df = BERTOPIC_MODEL.get_topic_info()
            print(f"Found {len(topic_info_df)} topics. Saving to {topic_info_path}...")
            wr.s3.to_parquet(df=topic_info_df, path=topic_info_path, index=False)
            print("Topic info file successfully saved to Gold layer.")
            
        else:
            print("No documents found to process for Topic Modeling. Skipping.")
            df_final['bertopic_id'] = -1 # Assign all as outliers

        # --- 6. Write final data to Gold Bucket ---
        print(f"Writing final data file to {gold_path}...")
        wr.s3.to_parquet(df=df_final, path=gold_path, index=False)
        print("Final data file successfully saved to Gold layer.")

        # --- 7. Clean up Silver Bucket ---
        print(f"Cleaning up intermediate files from {silver_path}...")
        wr.s3.delete_objects(path=silver_path)
        print("Cleanup complete.")

        # --- 8. Set final status to "COMPLETED" ---
        update_job_status(job_id, 'COMPLETED')
        print(f"Job {job_id} marked as COMPLETED.")

        return {
            'statusCode': 200,
            'body': json.dumps({'message': f'Job {job_id} completed successfully.'})
        }

    except Exception as e:
        # --- Global Error Handler ---
        print(f"[ERROR] A critical error occurred in the Stitcher: {e}")
        error_msg = f"Stitcher failed: {str(e)}"
        try:
            # Try to mark the job as FAILED for frontend visibility
            update_job_status(job_id, 'STITCHING_FAILED', error_msg)
        except Exception as db_e:
            print(f"Failed to even update status to FAILED: {db_e}")
        
        # This will return a 500 error to the API Gateway
        raise e