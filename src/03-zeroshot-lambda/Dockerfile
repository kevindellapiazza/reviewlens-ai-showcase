# --- STAGE 1: The Builder ---
# Use the official AWS SAM build image for binary compatibility
FROM public.ecr.aws/sam/build-python3.12 as builder

WORKDIR /app

COPY requirements.txt .

# Install dependencies into a target directory and clean up
RUN \
    pip install --no-cache-dir -r requirements.txt -t ./packages && \
    find /app/packages -type d -name "__pycache__" -exec rm -rf {} + && \
    find /app/packages -type f -name "*.pyc" -delete && \
    find /app/packages -type d -name "tests" -exec rm -rf {} +

# --- STAGE 2: The Final Lambda Image ---
FROM public.ecr.aws/lambda/python:3.12

WORKDIR /var/task

# Copy the pre-compiled libraries from the builder stage
COPY --from=builder /app/packages ./

# Copy the application and model download script
COPY main.py .
COPY download_models.py .

# --- Pre-download and cache the AI model ---
# 1. Define the *exact path* inside the image where models will be stored.
# 2. Set HF_HOME to this path so the download script saves models here.
# 3. Run the script to "bake" the models into the Docker image.
ENV HF_HOME=/var/task/model_cache
ENV TRANSFORMERS_CACHE=/var/task/model_cache

RUN python download_models.py

# Set the runtime command
# The HF_HOME env var MUST be set in Terraform to this same path:
# /var/task/model_cache
CMD [ "main.handler" ]