"""
ReviewLens AI: Model Downloader Script (Build-Time)

This script is executed *once* during the 'docker build' process
for the Stitcher Lambda.

It downloads the 'all-MiniLM-L6-v2' embedding model and saves it
to the /app/models directory, which is then copied into the
final Lambda image for instant cold-start loading.
"""

from sentence_transformers import SentenceTransformer
import os

MODEL_NAME = 'all-MiniLM-L6-v2'
SAVE_DIR = f'/app/models/{MODEL_NAME}'

print(f"--- Caching Model for Stitcher Lambda ---")
print(f"Downloading and caching model: {MODEL_NAME} to {SAVE_DIR}...")

os.makedirs(SAVE_DIR, exist_ok=True)

# Download and save the model
model = SentenceTransformer(MODEL_NAME)
model.save(SAVE_DIR)

print(f"Model caching complete.")

# Verification
if os.path.exists(os.path.join(SAVE_DIR, "pytorch_model.bin")):
    print(f"Verified {SAVE_DIR}/pytorch_model.bin exists.")
else:
    print(f"!!! WARNING: Model file not found after save.")