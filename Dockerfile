FROM python:3.8-slim-bullseye

# Bullseye ships with OpenSSL 1.1.1 which works with Atlas M0
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Create media directory
RUN mkdir -p media uploads/chat

# Run
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8002}
