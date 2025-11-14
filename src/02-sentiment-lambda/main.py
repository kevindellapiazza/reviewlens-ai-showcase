"""
ReviewLens AI: 02 - Sentiment Analysis Lambda

This function is the first AI step in the Step Functions workflow.
It receives a batch of reviews, performs sentiment analysis on each,
and passes the enriched data to the next step.

It loads a pre-baked model from the local filesystem (see Dockerfile)
to ensure minimal cold start time.
"""

import pandas as pd
from transformers import pipeline
import json
import re
import os
from io import StringIO

# --- Environment Variables ---
# Model name is configurable via Terraform
SENTIMENT_MODEL = os.environ.get(
    'SENTIMENT_MODEL', 
    'distilbert-base-uncased-finetuned-sst-2-english'
)

# --- Load Model (Global Scope) ---
# This code runs *once* during the Lambda cold start (INIT phase).
# The 'pipeline' function will automatically find the pre-baked model
# by reading the 'HF_HOME' environment variable set in Terraform
# (which MUST point to /var/task/model_cache).
print(f"Loading Sentiment Analysis model: {SENTIMENT_MODEL}...")
sentiment_pipeline = pipeline("sentiment-analysis", model=SENTIMENT_MODEL)

# Log the *actual* cache directory being used to confirm it's not /tmp
try:
    cache_dir = sentiment_pipeline.model.config.cache_dir
    print(f"Model successfully loaded from cache: {cache_dir}")
except AttributeError:
    print("Model loaded (cache path not inspectable).")


def sanitize_text(text: str) -> str:
    """
    Cleans a single text string from problematic characters.
    
    This provides "defense in depth" in case the splitter's
    sanitization is bypassed or fails.
    
    Args:
        text: The raw input string.

    Returns:
        A sanitized string.
    """
    if not isinstance(text, str): 
        return ""
    text = text.replace('&', 'and')
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    return text

def get_sentiment(text: str) -> str:
    """
    Applies sentiment analysis to a single text string with error handling.
    Truncates text to 512 tokens to prevent model errors.

    Args:
        text: A single review string.

    Returns:
        The sentiment label ('POSITIVE', 'NEGATIVE') or 'ERROR'.
    """
    try:
        # Truncate text to 512 tokens (model's max)
        return sentiment_pipeline(text[:512])[0]['label']
    except Exception as e:
        # If a single row fails, mark it as an error but don't stop the batch.
        print(f"Sentiment analysis failed for one row: {e}")
        return "ERROR"

def handler(event: dict, context: object) -> dict:
    """
    Main Lambda handler function triggered by Step Functions.

    Args:
        event: The payload from the previous state (Splitter).
               Contains 'job_id', 'batch_data', and 'config'.
        context: The Lambda runtime context (unused).

    Returns:
        The original event object, with 'batch_data' enriched
        with a new 'sentiment' column.
    """
    job_id = event.get('job_id', 'unknown_job')
    print(f"Sentiment Lambda started for job_id: {job_id}")

    try:
        # 1. Load the batch data passed from the previous step
        df = pd.read_json(StringIO(event['batch_data']), orient='split')

        # 2. Sanitize and analyze the text
        print(f"Applying sentiment analysis to {len(df)} rows for job {job_id}...")
        
        # Note: Text should already be sanitized, but we do it again
        # as a safety measure.
        df['full_review_text'] = df['full_review_text'].apply(sanitize_text)
        df['sentiment'] = df['full_review_text'].apply(get_sentiment)
        
        print(f"Sentiment analysis complete for job {job_id}.")

        # 3. Update the event payload with the enriched data
        # We overwrite 'batch_data' with the new DataFrame (as JSON)
        event['batch_data'] = df.to_json(orient='split')

        # 4. Return the entire event object for the next Lambda in the workflow
        return event

    except Exception as e:
        print(f"[ERROR] Batch failed for job_id {job_id}. Error: {e}")
        # Re-raise the exception to trigger the Step Function's 'Catch'
        # or 'Retry' logic, and send the message to the DLQ.
        raise e