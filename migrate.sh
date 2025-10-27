#!/bin/bash
# Migration script for Docker deployment

echo "Running database migrations..."
docker exec lms-backend alembic upgrade head

if [ $? -eq 0 ]; then
    echo "✅ Migrations completed successfully!"
else
    echo "❌ Migration failed! Check the logs above."
    exit 1
fi
