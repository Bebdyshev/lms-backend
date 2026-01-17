#!/bin/bash
set -e

# --- Configuration ---
BACKEND_DIR="~/projects/lms/" # Update this to your production path
BACKUP_DIR="~/projects/lms/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "🚀 Starting deployment at $TIMESTAMP..."

# 1. Pull latest changes
echo "📥 Pulling latest code..."
git pull origin main

# 2. Database Backup (Safety first!)
echo "💾 Creating database backup..."
mkdir -p $BACKUP_DIR
docker-compose exec -T postgres pg_dump -U myuser lms_db > $BACKUP_DIR/pre_deploy_backup_$TIMESTAMP.sql
echo "✅ Backup created: $BACKUP_DIR/pre_deploy_backup_$TIMESTAMP.sql"

# 3. Rebuild and restart containers
echo "🏗️ Rebuilding containers..."
docker-compose up -d --build backend

# 4. Run Migrations (using the dedicated migration service)
echo "🔄 Running database migrations..."
docker-compose run --rm migration

# 5. Verify deployment
echo "🔍 Verifying deployment..."
sleep 5
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "failed")

if [ "$HEALTH" == "200" ]; then
    echo "✅ Backend is healthy!"
else
    echo "❌ Health check failed with status: $HEALTH"
    echo "📜 Recent logs:"
    docker-compose logs --tail=20 backend
    exit 1
fi

echo "🎉 Deployment completed successfully!"
