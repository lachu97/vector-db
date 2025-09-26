#!/bin/bash
set -e

# ------------------------
# Config
# ------------------------
CONTAINER_NAME="vectordb_app"
PORT=8000
API_KEY=${API_KEY:-"test-key"}

# ------------------------
# Build and Run
# ------------------------
echo "Building Docker image..."
docker compose build

echo "Starting container..."
docker compose up -d

echo "Waiting for container to be healthy..."
while ! curl -s http://localhost:${PORT}/v1/health >/dev/null; do
  echo "Waiting for Vector DB to be ready..."
  sleep 3
done

echo "Vector DB is up and running at http://localhost:${PORT}"
echo "Use API key: $API_KEY"
