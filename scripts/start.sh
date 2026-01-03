#!/bin/bash
set -e

echo "🔄 Running database migrations..."
alembic upgrade head

echo "🚀 Starting application..."
exec uvicorn src.app:socket_app --host 0.0.0.0 --port 8000 --workers 4
