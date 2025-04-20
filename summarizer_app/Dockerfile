# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables to prevent interactive prompts during build
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PYTHONDONTWRITEBYTECODE=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed (e.g., by lxml)
# Update package list and install build-essential for C extensions if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    # Add any other system dependencies if required by your packages
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Make port 5000 available (Gunicorn will bind to this)
EXPOSE 5000

# Command to run the application using Gunicorn
# bind 0.0.0.0:5000 makes it accessible from outside the container
# workers 2: Adjust based on your expected load and container resources
# app:app refers to the Flask app instance named 'app' in 'app.py'
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]