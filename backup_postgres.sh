#!/bin/bash

# PostgreSQL Docker Backup Script
# Создает бэкап базы данных из Docker контейнера

# Конфигурация
# Автоматическое определение контейнера
if docker ps | grep -q "lms-postgres"; then
    CONTAINER_NAME="lms-postgres"
elif docker ps | grep -q "postgres-lms"; then
    CONTAINER_NAME="postgres-lms"
else
    echo "Ошибка: Не найден контейнер PostgreSQL (искал lms-postgres или postgres-lms)"
    exit 1
fi
DB_NAME="lms_db"
DB_USER="myuser"
BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${DATE}.dump"

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Создать директорию для бэкапов если не существует
mkdir -p $BACKUP_DIR

echo -e "${YELLOW}Начинаем создание бэкапа PostgreSQL...${NC}"

# Проверить, запущен ли контейнер
if ! docker ps | grep -q $CONTAINER_NAME; then
    echo -e "${RED}Ошибка: Контейнер $CONTAINER_NAME не запущен!${NC}"
    exit 1
fi

# Создать бэкап
echo -e "${YELLOW}Создание бэкапа в файл: $BACKUP_FILE${NC}"
docker exec $CONTAINER_NAME pg_dump -U $DB_USER -d $DB_NAME -F c -b > $BACKUP_FILE

# Проверить успешность
if [ $? -eq 0 ]; then
    # Получить размер файла
    FILE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}✓ Бэкап успешно создан!${NC}"
    echo -e "${GREEN}  Файл: $BACKUP_FILE${NC}"
    echo -e "${GREEN}  Размер: $FILE_SIZE${NC}"
    
    # Опционально: удалить старые бэкапы (старше 7 дней)
    echo -e "${YELLOW}Очистка старых бэкапов (старше 7 дней)...${NC}"
    find $BACKUP_DIR -name "*.dump" -mtime +7 -delete
    
    # Показать список всех бэкапов
    echo -e "${YELLOW}Доступные бэкапы:${NC}"
    ls -lh $BACKUP_DIR/*.dump 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
    
else
    echo -e "${RED}✗ Ошибка при создании бэкапа!${NC}"
    exit 1
fi

echo -e "${GREEN}Готово!${NC}"
