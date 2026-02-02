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
COPY scripts/ ./scripts/
COPY alembic.ini .

# Создание директории для uploads
RUN mkdir -p uploads

# Make start script executable
RUN chmod +x scripts/start.sh

# Открытие порта
EXPOSE 8000

CMD ["./scripts/start.sh"]