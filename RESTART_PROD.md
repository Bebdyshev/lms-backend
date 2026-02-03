# Restart Production Backend

После изменений в `docker-compose.yml` нужно перезапустить контейнеры для загрузки новых переменных окружения.

## Команды для продакшена:

```bash
# SSH to production server
ssh user@your-server

# Navigate to backend directory
cd /path/to/lms/backend

# Pull latest changes
git pull origin main

# Restart containers to reload environment variables
docker compose down
docker compose up -d

# Check logs
docker compose logs -f backend
```

## Или через GitHub Actions:

GitHub Actions автоматически задеплоит изменения, но для перезагрузки переменных окружения нужно:

```bash
# On production server
cd /path/to/lms/backend
docker compose restart backend
```

## Verify EMAIL_SENDER is loaded:

```bash
docker compose exec backend python -c "import os; print('EMAIL_SENDER:', os.getenv('EMAIL_SENDER'))"
```

Should output something like:
```
EMAIL_SENDER: Master Education <noreply@mail.mastereducation.kz>
```
