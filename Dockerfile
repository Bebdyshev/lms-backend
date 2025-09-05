FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Создание директории для uploads
RUN mkdir -p uploads

# Открытие порта
EXPOSE 8000

# Запуск приложения (Socket.IO wrapped ASGI app)
CMD ["uvicorn", "src.app:socket_app", "--host", "0.0.0.0", "--port", "8000"]
