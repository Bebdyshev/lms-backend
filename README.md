# LMS Backend - Docker Deployment

## 🚀 Быстрый старт

### 1. Подготовка
```bash
# Копировать .env.example в .env и настроить переменные
cp env.example .env
nano .env
```

### 2. Запуск
```bash
# Сделать скрипты исполняемыми
chmod +x deploy.sh backup.sh

# Запустить деплой
./deploy.sh
```

### 3. Проверка
```bash
# Статус контейнеров
docker compose ps

# Логи
docker compose logs -f backend
docker compose logs -f postgres

# Тест API
curl http://localhost:8000/docs
```

## 📁 Структура проекта
```
backend/
├── Dockerfile              # Образ для backend
├── docker-compose.yml      # Оркестрация контейнеров
├── .env                    # Переменные окружения
├── deploy.sh               # Скрипт деплоя
├── backup.sh               # Скрипт бэкапа
├── nginx/
│   └── nginx.conf         # Конфигурация Nginx
├── postgres/
│   └── init.sql           # Инициализация БД
└── uploads/                # Загруженные файлы
```

## 🔧 Управление

### Команды Docker Compose
```bash
# Запуск
docker compose up -d

# Остановка
docker compose down

# Перезапуск
docker compose restart

# Логи
docker compose logs -f [service_name]

# Обновление
docker compose pull
docker compose up -d
```

### Бэкапы
```bash
# Создание бэкапа
./backup.sh

# Восстановление (если нужно)
docker exec -i lms-postgres psql -U myuser lms_db < backup_file.sql
```

## 🌐 Доступ
- **Backend API:** http://132.220.216.36:8000
- **API Docs:** http://132.220.216.36:8000/docs
- **Database:** localhost:5432
- **Nginx:** http://132.220.216.36

## 🔒 Безопасность
- Измените пароли в .env файле
- Настройте firewall (ufw)
- Ограничьте доступ по IP в Azure NSG
- Используйте SSL сертификаты для продакшна

## 📊 Мониторинг
```bash
# Статус сервисов
docker compose ps

# Использование ресурсов
docker stats

# Логи в реальном времени
docker compose logs -f
```
