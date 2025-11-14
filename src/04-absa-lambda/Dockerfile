# --- STAGE 1: The Builder ---
# Use the official AWS SAM build image for Python 3.11.
# We use 3.11 for this specific Lambda to ensure maximum stability
# with complex dependencies like torch, transformers, and awswrangler.
FROM public.ecr.aws/sam/build-python3.11 as builder

# Switch to root to install build-time system dependencies
USER root

# Create the build directory and model cache directory
# /build_app is a temporary directory *only* for the builder stage
RUN mkdir -p /build_app/models && chown 1000:1000 /build_app
WORKDIR /build_app

# Install system-level dependencies required for building Python wheels
# (e.g., for 'tokenizers' or other C-based libraries)
RUN yum install -y git cmake gcc-c++ make automake autoconf libtool protobuf-devel && yum clean all

# --- Install Python Dependencies ---
# 1. Install PyTorch (CPU-only version) *first*.
#    This prevents 'transformers' from trying to install a large GPU-enabled build.
RUN pip install --no-cache-dir torch==2.1.0+cpu --index-url https://download.pytorch.org/whl/cpu

# 2. Install all other Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Run the model download script to "bake-in" the mDeBERTa model
COPY download_models.py .
RUN python download_models.py

# Verification step to check build contents
RUN echo "DEBUG: Verifying final contents of /build_app/models..." && \
    ls -lR /build_app/models


# --- STAGE 2: The Final Lambda Image ---
# Use the official Python 3.11 runtime image
FROM public.ecr.aws/lambda/python:3.11

WORKDIR /var/task

# CRITICAL: We do *NOT* need 'git' in the final runtime image.
# Omitting it saves >150MB from the final image.
# RUN yum install -y git && yum clean all  <-- This line was removed

# Copy installed Python packages from the builder stage
# This is the standard path where 'sam/build' stores packages
COPY --from=builder /var/lang/lib/python3.11/site-packages ./packages
# Add the packages directory to the Python path
ENV PYTHONPATH "${LAMBDA_TASK_ROOT}/packages:${PYTHONPATH}"

# --- Copy Baked-in AI Model ---
# Copy the entire /models directory from the builder stage
# to the final image.
COPY --from=builder /build_app/models /var/task/models

# Copy the Lambda handler code
COPY main.py .
CMD [ "main.handler" ]