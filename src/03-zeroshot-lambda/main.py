"""
ReviewLens AI: 03 - Zero-Shot Classification Lambda

This function is the second AI step in the Step Functions workflow.
It receives a batch of reviews (already processed by the sentiment-lambda)
and applies zero-shot classification to categorize each review.

It uses a set of 'candidate_labels' that are passed *dynamically*
from the 'splitter-lambda' (originating from the user's upload).
"""

import pandas as pd
from transformers import pipeline
import json
import os
from io import StringIO
from typing import List

# --- Environment Variables ---
ZEROSHOT_MODEL = os.environ.get(
    'ZEROSHOT_MODEL', 
    'typeform/distilbert-base-uncased-mnli'
)

# --- Global Constants ---
# Define a robust default list of labels in case the user provides none.
DEFAULT_ZERO_SHOT_LABELS = 'price,quality,shipping,customer service,fit,fabric'

# --- Load Model (Global Scope) ---
# This code runs *once* during the Lambda cold start (INIT phase).
# It loads the pre-baked model from the /var/task/model_cache directory.
print(f"Loading Zero-Shot Classification model: {ZEROSHOT_MODEL}...")
zero_shot_classifier = pipeline("zero-shot-classification", model=ZEROSHOT_MODEL)

# Log the *actual* cache directory to confirm it's not /tmp
try:
    cache_dir = zero_shot_classifier.model.config.cache_dir
    print(f"Model successfully loaded from cache: {cache_dir}")
except AttributeError:
    print("Model loaded (cache path not inspectable).")


def get_top_topic(review_text: str, candidate_labels: List[str]) -> str:
    """
    Applies zero-shot classification to a single text string.
    Truncates text to 512 tokens to prevent model errors.
    """
    
    if not review_text or not review_text.strip():
        return "N/A (No text provided)"

    try:
        # Check if the labels list is valid
        if not candidate_labels:
            print(f"Warning: Empty candidate labels for text: {review_text[:50]}...")
            return "N/A (No labels provided)"
        
        # Truncate text to stay within model limits
        return zero_shot_classifier(review_text[:512], candidate_labels)['labels'][0]
    
    except Exception as e:
        # Log the actual error
        print(f"Error in get_top_topic for text '{review_text[:50]}...': {e}")
        return "ERROR"

def handler(event: dict, context: object) -> dict:
    """
    Main Lambda handler function triggered by Step Functions.

    Args:
        event: The payload from the previous state (Sentiment).
               Contains 'job_id', 'batch_data', and 'config'.
        context: The Lambda runtime context (unused).

    Returns:
        The original event object, with 'batch_data' enriched
        with a new 'zero_shot_topic' column.
    """
    job_id = event.get('job_id', 'unknown_job')
    print(f"Zero-Shot Lambda started for job_id: {job_id}")

    try:
        # --- 1. Load Dynamic Labels from Config ---
        config = event.get('config', {})
        
        # Get dynamic labels from the event (sent by the user).
        labels_str = config.get('zero_shot_labels')
        
        # If the user provided no labels (None or ""), use the defaults.
        if not labels_str:
            print("No dynamic labels provided. Using default labels.")
            labels_str = DEFAULT_ZERO_SHOT_LABELS
        else:
            print(f"Using dynamic labels provided by user: {labels_str[:100]}...")
            
        # Clean the list (removes empty strings if user adds trailing commas)
        candidate_labels = [
            label.strip() for label in labels_str.split(',') if label.strip()
        ]

        # --- 2. Load the Batch Data ---
        batch_data_str = event.get('batch_data')
        if not batch_data_str:
            raise ValueError("batch_data is missing from the event.")
        
        df = pd.read_json(StringIO(batch_data_str), orient='split')
        print(f"Successfully loaded {len(df)} rows for job {job_id}.")

        # --- 3. Run the Analysis ---
        print(f"Applying zero-shot classification to {len(df)} rows...")
        df['zero_shot_topic'] = df['full_review_text'].apply(
            lambda text: get_top_topic(text, candidate_labels)
        )
        print("Zero-Shot classification complete.")

        # --- 4. Update and Return the Event Payload ---
        event['batch_data'] = df.to_json(orient='split')
        return event

    except Exception as e:
        print(f"[ERROR] Batch failed for job_id {job_id}. Error: {e}")
        # Re-raise the exception to trigger the Step Function's 'Catch'
        # or 'Retry' logic, and send the message to the DLQ.
        raise e