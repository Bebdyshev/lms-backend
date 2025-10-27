#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Run Alembic migrations
POSTGRES_URL="${POSTGRES_URL}" alembic upgrade head
