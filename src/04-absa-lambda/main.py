"""
ReviewLens AI: 04 - ABSA Lambda

This function is the final AI step in the Step Functions workflow.
It is the most critical function in the AI pipeline.

Responsibilities:
1.  Loads the pre-baked mDeBERTa model from the local filesystem.
2.  Reads the batch data (enriched by sentiment and zero-shot).
3.  Reads dynamic 'absa_labels' from the event 'config'.
4.  Performs aspect-based sentiment analysis (ABSA) using the
    Zero-Shot pipeline with multi_label=True.
5.  Saves the final, fully-enriched batch as a Parquet file
    in the S3 Silver Bucket.
6.  Atomically increments the 'processed_batches' counter in
    DynamoDB to track job progress.
"""

import os
import json
import pandas as pd
import awswrangler as wr
import boto3
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from io import StringIO
from typing import List

# --- Environment Variables ---
SILVER_BUCKET_NAME = os.environ['SILVER_BUCKET_NAME']
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']

# This path MUST match the 'COPY' destination in the Dockerfile
MODEL_DIR = os.environ.get(
    "MODEL_DIR", 
    "/var/task/models/mDeBERTa-v3-base-mnli-xnli"
)

# --- Global Constants ---
DEFAULT_ABSA_LABELS = "slow delivery,fast delivery,damaged box,good quality,poor quality,good fit,tight fit,good price,expensive"
DEFAULT_THRESHOLD = "0.6"

# --- Model Loading (Cold Start) ---
# This code runs *once* during the Lambda INIT phase.
# We explicitly load the model from the "baked-in" local directory
# to ensure zero download time during cold starts.
print(f"Loading Zero-Shot tokenizer from local path: {MODEL_DIR}...")
try:
    # local_files_only=True: Forces transformers to *only* look
    # in the MODEL_DIR and fail if it's not there. This prevents
    # any accidental (and slow) downloads from the internet.
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_DIR, local_files_only=True
    )
    
    print(f"Loading Zero-Shot model from local path: {MODEL_DIR}...")
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_DIR, local_files_only=True
    )
    
    print("Initializing zero-shot-classification pipeline...")
    zero_shot_classifier = pipeline(
        "zero-shot-classification",
        model=model,
        tokenizer=tokenizer
    )
    print("Zero-Shot classifier (for ABSA) loaded successfully.")
except Exception as e:
    print(f"FATAL: Failed to load model components from {MODEL_DIR}: {e}")
    # If the model fails to load, we raise the exception to
    # fail the Lambda init, which AWS will retry.
    raise e

# --- AWS Clients (Global Scope) ---
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)


def get_aspects(review_text: str, aspect_labels: List[str], threshold: float) -> str:
    """
    Applies zero-shot classification to find all matching
    Aspect-Sentiment Pairs (ASPs) that meet the score threshold.

    Args:
        review_text: The raw review text.
        aspect_labels: A list of candidate labels (e.g., "slow delivery").
        threshold: The minimum confidence score (e.g., 0.6) to keep a label.

    Returns:
        A comma-separated string of matching aspects, or "N/A".
    """
    if not isinstance(review_text, str) or not review_text.strip():
        return "N/A"

    try:
        if not aspect_labels:
            print(f"Warning: Empty aspect labels for text: {review_text[:50]}...")
            return "N/A (No labels provided)"

        # Truncate text to avoid model errors
        truncated_text = " ".join(review_text.split()[:400])
        
        results = zero_shot_classifier(
            truncated_text,
            aspect_labels,
            multi_label=True # Critical for finding multiple aspects
        )

        matching_aspects = []
        for label, score in zip(results['labels'], results['scores']):
            if score >= threshold:
                # Store with score for validation
                matching_aspects.append(f"{label} ({score:.2f})")

        if not matching_aspects:
            return "N/A"
        
        return ", ".join(matching_aspects)

    except Exception as e:
        print(f"Error during Zero-Shot prediction for text '{review_text[:50]}...': {e}")
        return "PREDICTION_ERROR"


def handler(event: dict, context: object) -> dict:
    """
    Main Lambda handler triggered by Step Functions.

    Args:
        event: The payload from the previous state (ZeroShot).
               Contains 'job_id', 'batch_data', and 'config'.
        context: The Lambda runtime context.

    Returns:
        A dict with a 'status' key, as this is the
        end of the successful Step Function path.
    """
    job_id = event.get('job_id')
    if not job_id:
        print("FATAL: job_id missing from event.")
        raise ValueError("job_id is required but was not found in the event.")

    print(f"ABSA Lambda started for job_id: {job_id}")

    try:
        # --- 1. Get Dynamic Config ---
        config = event.get('config', {})
        
        # Get dynamic labels, falling back to defaults
        labels_str = config.get('absa_labels', DEFAULT_ABSA_LABELS)
        if not labels_str:
            labels_str = DEFAULT_ABSA_LABELS
            print("No dynamic ABSA labels provided. Using defaults.")
        
        # Clean the list
        aspect_sentiment_labels = [
            label.strip() for label in labels_str.split(',') if label.strip()
        ]
        
        # Get score threshold
        score_threshold = float(os.environ.get("SCORE_THRESHOLD", DEFAULT_THRESHOLD))

        # --- 2. Load DataFrame from Event ---
        batch_data_str = event.get('batch_data')
        if not batch_data_str:
            raise ValueError("batch_data is missing from the event.")
        
        df = pd.read_json(StringIO(batch_data_str), orient='split')
        print(f"Successfully loaded {len(df)} rows for job {job_id}.")

        review_col = 'full_review_text'
        if review_col not in df.columns:
            raise ValueError(f"Column '{review_col}' not found in DataFrame.")

        # --- 3. Apply Zero-Shot ABSA Enrichment ---
        print(f"Applying Zero-Shot ABSA to {len(df)} rows...")
        df['aspects'] = df[review_col].fillna("").astype(str).apply(
            lambda x: get_aspects(x, aspect_sentiment_labels, score_threshold)
        )
        print(f"Zero-Shot ABSA complete for job {job_id}.")

        # --- 4. Save Enriched Batch to S3 (Silver Layer) ---
        
        # Use the Lambda's unique request ID as the filename.
        # This is a robust pattern that prevents any parallel
        # executions from overwriting each other's files.
        aws_request_id = getattr(context, 'aws_request_id', 'unknown_request_id')
        output_path = f"s3://{SILVER_BUCKET_NAME}/processed-batches/{job_id}/{aws_request_id}.parquet"

        print(f"Saving enriched batch to {output_path}...")
        wr.s3.to_parquet(df=df, path=output_path, index=False)
        print(f"Batch successfully saved to {output_path}.")

        # --- 5. Atomically Update DynamoDB Job Status ---
        print(f"Incrementing processed_batches count for job {job_id}...")
        response = table.update_item(
            Key={'job_id': job_id},
            # 'ADD :inc' is an atomic counter. It's safe to run in parallel
            # and avoids race conditions.
            UpdateExpression="ADD processed_batches :inc",
            ExpressionAttributeValues={":inc": 1},
            ReturnValues="UPDATED_NEW"
        )
        print(f"DynamoDB update complete. New count: {response.get('Attributes', {}).get('processed_batches', 'N/A')}")

        print(f"ABSA Lambda finished successfully for job_id: {job_id}")
        
        # This is the last step in the SFN, so we just return a success
        # The 'OutputPath' in the State Machine definition will drop this
        # and pass nothing, which is fine.
        return {'status': 'SUCCESS'}

    except Exception as e:
        print(f"[ERROR] Batch failed for job_id {job_id}. Error: {e}")
        # Re-raise the exception to trigger the Step Function's 'Catch'
        # or 'Retry' logic, and send the message to the DLQ.
        raise e