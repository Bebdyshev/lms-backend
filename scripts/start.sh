#!/bin/bash
set -e

# Run migrations
echo "Running database migrations..."
alembic upgrade head

# Start server
echo "Starting server..."
uvicorn src.app:app --host 0.0.0.0 --port 8000
