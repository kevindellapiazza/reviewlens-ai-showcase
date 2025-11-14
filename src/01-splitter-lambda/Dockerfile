# --- STAGE 1: The Builder ---
# Use the official AWS SAM build image. This image mirrors the
# final Lambda runtime environment (Amazon Linux), ensuring any
# compiled binaries (like from pandas) are compatible.
FROM public.ecr.aws/sam/build-python3.12 as builder

# Set the working directory
WORKDIR /app

# Copy only the requirements file first to leverage Docker's build cache.
COPY requirements.txt .

# Install dependencies into a local directory 'packages'
# This compiles pandas and its dependencies using the Amazon Linux env.
RUN pip install --no-cache-dir -r requirements.txt -t ./packages

# --- STAGE 2: The Final Lambda Image ---
# Use the official AWS Lambda base image. This is lightweight
# and contains only the necessary runtime interface.
FROM public.ecr.aws/lambda/python:3.12

# Set the working directory
WORKDIR /var/task

# Copy *only* the installed packages from the 'builder' stage.
# We don't need the build tools (like gcc) in the final image.
COPY --from=builder /app/packages ./

# Copy the Lambda handler code
COPY main.py .

# Set the CMD to the entry point for the Lambda function.
CMD [ "main.handler" ]