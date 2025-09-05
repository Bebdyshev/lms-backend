#!/bin/bash

echo "💾 Creating database backup..."

# Создание директории для бэкапов если не существует
mkdir -p backups

# Создание бэкапа с timestamp
BACKUP_FILE="backups/backup_$(date +%Y%m%d_%H%M%S).sql"

# Создание бэкапа из PostgreSQL контейнера
docker exec lms-postgres pg_dump -U myuser lms_db > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Backup created successfully: $BACKUP_FILE"
    echo "📁 Backup size: $(du -h "$BACKUP_FILE" | cut -f1)"
else
    echo "❌ Backup failed!"
    exit 1
fi
