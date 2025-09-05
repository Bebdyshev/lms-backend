#!/bin/bash

echo "🚀 Deploying LMS Backend..."

# Остановка существующих контейнеров
echo "📦 Stopping existing containers..."
docker compose down

# Сборка и запуск
echo "🔨 Building and starting containers..."
docker compose up -d --build

# Проверка статуса
echo "✅ Checking container status..."
docker compose ps

# Проверка логов
echo "📋 Container logs:"
docker compose logs --tail=20

echo "🎉 Deployment completed!"
echo "🌐 Backend API: http://132.220.216.36:8000"
echo "📚 API Docs: http://132.220.216.36:8000/docs"
echo "🗄️  Database: localhost:5432"
