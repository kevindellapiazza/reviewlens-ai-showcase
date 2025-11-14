"""
ReviewLens AI: Model Downloader Script (Build-Time)

This script is executed *once* during the 'docker build' process
for the ABSA Lambda.

It uses 'snapshot_download' to save the model files to a specific
local directory inside the builder, which is then copied to the
final image. This is an alternative MLOps pattern to using HF_HOME.
"""

from huggingface_hub import snapshot_download
import os

# --- Model Configuration ---
MODEL_NAME = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
# This subdirectory *must* match the MODEL_DIR env var in main.py
SAVE_SUBDIR = "mDeBERTa-v3-base-mnli-xnli"
# This is the temporary build-time path
SAVE_DIR = os.path.join("/build_app/models", SAVE_SUBDIR)

print(f"Ensuring model save directory exists: {SAVE_DIR}")
os.makedirs(SAVE_DIR, exist_ok=True)

print(f"Downloading model {MODEL_NAME} files to {SAVE_DIR}...")

# Download all model files (config, tokenizer, weights)
snapshot_download(
    repo_id=MODEL_NAME,
    local_dir=SAVE_DIR,
    local_dir_use_symlinks=False, # Use file copies, not symlinks
)

print(f"Model {MODEL_NAME} downloaded successfully to {SAVE_DIR}.")

# --- Verification Step ---
# Check for the existence of model weights (either .bin or .safetensors)
model_file_bin = os.path.join(SAVE_DIR, "pytorch_model.bin")
model_file_sf = os.path.join(SAVE_DIR, "model.safetensors")

if os.path.exists(model_file_bin):
    print(f"Confirmed {model_file_bin} exists.")
elif os.path.exists(model_file_sf):
    print(f"Confirmed {model_file_sf} exists.")
else:
    print(f"!!! WARNING: Neither pytorch_model.bin nor model.safetensors was found!")
    # This check is useful but we don't fail the build,
    # as other files might be present.