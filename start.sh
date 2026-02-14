#!/bin/bash

# Wait for database to be ready (optional but recommended)
echo "Waiting for database..."
# Simple sleep for demo, better to use a wait-for-it script or check DB status
sleep 5

# Run migrations
echo "Running database migrations..."
alembic upgrade head

# Start the application
echo "Starting FastAPI application..."
uvicorn main:app --host 0.0.0.0 --port 8000
