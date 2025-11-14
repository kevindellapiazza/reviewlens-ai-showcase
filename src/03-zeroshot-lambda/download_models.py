"""
ReviewLens AI: Model Downloader Script (Build-Time)

This script is executed *once* during the 'docker build' process
for the Zero-Shot Lambda.

It reads the 'ZEROSHOT_MODEL' env var (the same one used by main.py)
and "bakes" the model into the container image at /var/task/model_cache.
"""

import os
from transformers import pipeline

# Read the model name from the environment variable.
# Fallback to the same default as main.py for consistency.
MODEL_TO_DOWNLOAD = os.environ.get(
    'ZEROSHOT_MODEL', 
    'typeform/distilbert-base-uncased-mnli'
)

print(f"--- Caching Model for Zero-Shot Lambda ---")
print(f"Downloading and caching model: {MODEL_TO_DOWNLOAD}...")

# This command initializes the pipeline, which downloads and caches
# all necessary files to the path specified by the HF_HOME env var.
pipeline("zero-shot-classification", model=MODEL_TO_DOWNLOAD)

print(f"Model caching complete for {MODEL_TO_DOWNLOAD}.")