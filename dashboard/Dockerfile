# 1. Use the official Python base image as a foundation
FROM python:3.12-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy the requirements file first to leverage Docker layer caching
COPY requirements.txt .

# 4. Install the Python dependencies
RUN pip install -r requirements.txt --no-cache-dir

# 5. Copy the rest of the application code
COPY . .

# 6. Expose the port Streamlit runs on
EXPOSE 8501

# 7. Define the command to run the Streamlit app when the container starts
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]