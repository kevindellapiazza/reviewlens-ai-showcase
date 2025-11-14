"""
ReviewLens AI: Model Downloader Script (Build-Time)

This script is executed *once* during the 'docker build' process.
It downloads the specified model from Hugging Face and saves it
to the cache directory defined by the HF_HOME environment variable
(e.g., /var/task/model_cache).

This "bakes" the model into the container image, eliminating the need
to download it at runtime and ensuring a minimal cold start.
"""

import os
from transformers import pipeline

# Read the model name from the environment variable set in Terraform.
# Fallback to the same default as main.py for consistency.
MODEL_TO_DOWNLOAD = os.environ.get(
    'SENTIMENT_MODEL', 
    'distilbert-base-uncased-finetuned-sst-2-english'
)

print(f"--- Caching Model for Sentiment Lambda ---")
print(f"Downloading and caching model: {MODEL_TO_DOWNLOAD}...")

# This command initializes the pipeline. By doing so, it finds,
# downloads, and caches all necessary files (config, model weights,
# tokenizer) to the path specified by the HF_HOME env var.
pipeline("sentiment-analysis", model=MODEL_TO_DOWNLOAD)

print(f"Model caching complete for {MODEL_TO_DOWNLOAD}.")