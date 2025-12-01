#!/bin/bash

# PostgreSQL Docker Restore Script
# Восстанавливает базу данных из бэкапа

# Конфигурация
CONTAINER_NAME="lms-postgres"
DB_NAME="lms_db"
DB_USER="myuser"
BACKUP_DIR="./backups"

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка аргументов
if [ -z "$1" ]; then
    echo -e "${YELLOW}Использование: $0 <файл_бэкапа>${NC}"
    echo -e "${YELLOW}Доступные бэкапы:${NC}"
    ls -lh $BACKUP_DIR/*.dump 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
    exit 1
fi

BACKUP_FILE=$1

# Проверить существование файла
if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}Ошибка: Файл $BACKUP_FILE не найден!${NC}"
    exit 1
fi

# Проверить, запущен ли контейнер
if ! docker ps | grep -q $CONTAINER_NAME; then
    echo -e "${RED}Ошибка: Контейнер $CONTAINER_NAME не запущен!${NC}"
    exit 1
fi

echo -e "${YELLOW}Восстановление базы данных из: $BACKUP_FILE${NC}"
echo -e "${RED}ВНИМАНИЕ: Это удалит все текущие данные в базе!${NC}"
read -p "Продолжить? (yes/no): " -r
if [[ ! $REPLY =~ ^yes$ ]]; then
    echo -e "${YELLOW}Отменено.${NC}"
    exit 0
fi

# Остановить все подключения к базе
echo -e "${YELLOW}Остановка подключений к базе данных...${NC}"
docker exec -t $CONTAINER_NAME psql -U $DB_USER -d postgres -c "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = '$DB_NAME' AND pid <> pg_backend_pid();"

# Удалить базу если существует
echo -e "${YELLOW}Удаление старой базы данных...${NC}"
docker exec -t $CONTAINER_NAME psql -U $DB_USER -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"

# Создать новую базу
echo -e "${YELLOW}Создание новой базы данных...${NC}"
docker exec -t $CONTAINER_NAME psql -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME;"

# Восстановить данные
echo -e "${YELLOW}Восстановление данных...${NC}"
docker exec -i $CONTAINER_NAME pg_restore -U $DB_USER -d $DB_NAME -v < $BACKUP_FILE

# Проверить успешность
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ База данных успешно восстановлена!${NC}"
else
    echo -e "${RED}✗ Ошибка при восстановлении!${NC}"
    exit 1
fi

echo -e "${GREEN}Готово!${NC}"
