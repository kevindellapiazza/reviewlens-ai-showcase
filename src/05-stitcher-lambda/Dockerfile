# --- STAGE 1: The Builder ---
# Use the official AWS SAM build image for Python 3.11.
# This is critical for compiling 'bertopic' dependencies like 'hdbscan'.
FROM public.ecr.aws/sam/build-python3.11 as builder

# Switch to root to install build-time system dependencies
USER root

# Create the build directory and model cache directory
RUN mkdir -p /app/models && chown 1000:1000 /app
WORKDIR /app

# Install system-level dependencies required for building C++/C packages
RUN yum install -y gcc-c++ make cmake && yum clean all

# Copy requirements file first to leverage cache
COPY requirements.txt .

# Install all Python dependencies into a local 'packages' directory
RUN pip install --no-cache-dir -r requirements.txt -t ./packages

# --- Pre-download and "bake-in" the embedding model ---

# Set the PYTHONPATH so the 'python' executable can find the
# libraries we just installed into the './packages' directory.
ENV PYTHONPATH="/app/packages:${PYTHONPATH}"

# We create a separate script for clarity
COPY download_model.py .
RUN python download_model.py

# Verification step
RUN echo "DEBUG: Verifying final contents of /app/models..." && \
    ls -lR /app/models


# --- STAGE 2: The Final Lambda Image ---
# Use the official Python 3.11 runtime image
FROM public.ecr.aws/lambda/python:3.11

WORKDIR /var/task

# Copy *only* the installed packages from the builder stage
COPY --from=builder /app/packages ./packages

# Copy the pre-downloaded model from the builder stage
COPY --from=builder /app/models /var/task/models

# Add the 'packages' directory to the Python import path
# (This is for the Lambda *runtime*)
ENV PYTHONPATH "${LAMBDA_TASK_ROOT}/packages:${PYTHONPATH}"

# Copy the final application code.
COPY main.py .

# Set the command for the Lambda handler.
CMD [ "main.handler" ]