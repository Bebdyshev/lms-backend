# 🐰 RabbitMQ Integration Guide - Подключение к обновлениям пользователей

## 📋 Обзор

Это руководство для подключения любого сервиса (LMS, SAT, IELTS и т.д.) к **Central Auth System** через RabbitMQ для автоматической синхронизации пользователей в реальном времени.

---

## 🎯 Что вы получите

- ✅ Автоматическое создание пользователей при регистрации в Central Auth
- ✅ Автоматическое обновление данных пользователей (имя, роль, пароль)
- ✅ Автоматическая деактивация при удалении пользователей
- ✅ Контроль доступа через `allowed_services_json` (только нужные пользователи попадут в ваш сервис)

---

## 🔧 Шаг 1: Подготовка

### 1.1. Установка зависимостей

**Python:**
```bash
pip install pika==1.3.2
```

**Node.js:**
```bash
npm install amqplib
```

**Go:**
```bash
go get github.com/rabbitmq/amqp091-go
```

### 1.2. Конфигурация

Добавьте в `.env` файл:

```bash
# RabbitMQ Configuration
RABBITMQ_URL=amqp://auth:NXsgvjB5Ff3VWHiKra1Boc3YIoXWAQYE2FBAikXNGg4=@185.129.48.238:5672/
RABBITMQ_EXCHANGE=user_events

# Или для продакшн через домен
RABBITMQ_URL=amqp://auth:NXsgvjB5Ff3VWHiKra1Boc3YIoXWAQYE2FBAikXNGg4=@rabbitmqauth.mastereducation.kz:5672/
```

**Параметры:**
- **Host**: `185.129.48.238` или `rabbitmqauth.mastereducation.kz`
- **Port**: `5672` (AMQP)
- **User**: `auth`
- **Password**: `NXsgvjB5Ff3VWHiKra1Boc3YIoXWAQYE2FBAikXNGg4=`
- **Exchange**: `user_events` (type: `topic`)

---

## 📡 Шаг 2: События (Events)

### События которые публикуются:

| Routing Key | Событие | Когда происходит |
|------------|---------|------------------|
| `user.created` | Создание пользователя | Новая регистрация в Central Auth |
| `user.updated` | Обновление пользователя | Изменение данных (имя, роль, пароль, permissions) |
| `user.deleted` | Удаление пользователя | Удаление из Central Auth |

### Формат сообщения:

```json
{
  "event_type": "user.created",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "student@example.com",
    "first_name": "Иван",
    "last_name": "Иванов",
    "password_hash": "$2b$12$...",
    "role": "student",
    "is_active": true,
    "allowed_services_json": "[\"lms\", \"sat\"]"
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

**Важные поля:**
- `allowed_services_json` - JSON строка с массивом сервисов: `["lms", "sat", "ielts"]`
- `password_hash` - уже захешированный пароль (bcrypt)
- `role` - роль пользователя: `student`, `teacher`, `curator`, `admin`

---

## 🐍 Шаг 3: Реализация (Python Example)

### 3.1. Создайте Consumer

Создайте файл `rabbitmq_consumer.py`:

```python
import json
import logging
import os
import pika
import threading
from typing import Dict, Any

logger = logging.getLogger(__name__)

class RabbitMQConsumer:
    def __init__(self, rabbitmq_url: str, exchange: str, service_name: str):
        self.rabbitmq_url = rabbitmq_url
        self.exchange = exchange
        self.service_name = service_name  # 'lms', 'sat', 'ielts'
        self.connection = None
        self.channel = None
        
    def connect(self):
        """Подключение к RabbitMQ"""
        # Подключение
        parameters = pika.URLParameters(self.rabbitmq_url)
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        
        # Объявляем exchange
        self.channel.exchange_declare(
            exchange=self.exchange,
            exchange_type='topic',
            durable=True
        )
        
        # Создаем уникальную очередь для вашего сервиса
        queue_name = f'{self.service_name}_user_events'
        self.channel.queue_declare(queue=queue_name, durable=True)
        
        # Привязываем к routing keys
        routing_keys = ['user.created', 'user.updated', 'user.deleted']
        for routing_key in routing_keys:
            self.channel.queue_bind(
                exchange=self.exchange,
                queue=queue_name,
                routing_key=routing_key
            )
        
        logger.info(f"✅ Connected to RabbitMQ: {self.exchange}")
        return queue_name
    
    def has_service_access(self, user_data: Dict[str, Any]) -> bool:
        """Проверка доступа пользователя к вашему сервису"""
        role = user_data.get('role', 'student')
        
        # Не-студенты имеют доступ ко всем сервисам
        if role != 'student':
            return True
        
        # Для студентов проверяем allowed_services_json
        allowed_services = user_data.get('allowed_services_json', '[]')
        if isinstance(allowed_services, str):
            allowed_services = json.loads(allowed_services)
        
        return self.service_name in allowed_services
    
    def handle_user_created(self, user_data: Dict[str, Any]):
        """Обработка создания пользователя"""
        # Проверка доступа
        if not self.has_service_access(user_data):
            logger.info(f"⏭️  Skipping user {user_data.get('email')} - no {self.service_name} access")
            return
        
        # TODO: Ваша логика создания пользователя в БД
        # Например:
        # db.users.create({
        #     'email': user_data['email'],
        #     'name': f"{user_data['first_name']} {user_data['last_name']}",
        #     'password_hash': user_data['password_hash'],
        #     'role': user_data['role'],
        # })
        
        logger.info(f"✅ User created: {user_data.get('email')}")
    
    def handle_user_updated(self, user_data: Dict[str, Any]):
        """Обработка обновления пользователя"""
        # Проверка доступа
        if not self.has_service_access(user_data):
            # Деактивировать пользователя если потерял доступ
            # TODO: db.users.update(email=user_data['email'], is_active=False)
            logger.info(f"🔒 User deactivated: {user_data.get('email')}")
            return
        
        # TODO: Ваша логика обновления пользователя
        logger.info(f"✅ User updated: {user_data.get('email')}")
    
    def handle_user_deleted(self, user_data: Dict[str, Any]):
        """Обработка удаления пользователя"""
        # TODO: Мягкое удаление (деактивация)
        # db.users.update(email=user_data['email'], is_active=False)
        
        logger.info(f"🗑️  User deactivated: {user_data.get('email')}")
    
    def process_message(self, ch, method, properties, body):
        """Обработка входящего сообщения"""
        try:
            # Парсим сообщение
            message = json.loads(body)
            event_type = message.get('event_type')
            user_data = message.get('user', {})
            
            logger.info(f"📨 Received: {event_type} for {user_data.get('email')}")
            
            # Обработка по типу события
            if event_type == 'user.created':
                self.handle_user_created(user_data)
            elif event_type == 'user.updated':
                self.handle_user_updated(user_data)
            elif event_type == 'user.deleted':
                self.handle_user_deleted(user_data)
            
            # Подтверждаем обработку
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}")
            # Отклоняем и возвращаем в очередь
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def start_consuming(self):
        """Запуск потребления сообщений"""
        queue_name = self.connect()
        
        # QoS - по одному сообщению за раз
        self.channel.basic_qos(prefetch_count=1)
        
        # Начинаем слушать
        self.channel.basic_consume(
            queue=queue_name,
            on_message_callback=self.process_message
        )
        
        logger.info("🚀 Starting to consume messages...")
        self.channel.start_consuming()


def start_consumer_thread(service_name: str):
    """Запуск consumer в фоновом потоке"""
    rabbitmq_url = os.getenv('RABBITMQ_URL')
    exchange = os.getenv('RABBITMQ_EXCHANGE', 'user_events')
    
    consumer = RabbitMQConsumer(rabbitmq_url, exchange, service_name)
    
    def run():
        try:
            consumer.start_consuming()
        except Exception as e:
            logger.error(f"❌ Consumer error: {e}")
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info("🧵 RabbitMQ consumer thread started")
```

### 3.2. Интегрируйте в ваше приложение

В вашем главном файле приложения (например, `app.py` для FastAPI):

```python
from rabbitmq_consumer import start_consumer_thread

# При старте приложения
start_consumer_thread(service_name='lms')  # Замените на 'sat', 'ielts' и т.д.
```

### 3.3. Реализуйте обработчики

Замените `TODO` комментарии на реальную логику работы с вашей БД:

```python
def handle_user_created(self, user_data: Dict[str, Any]):
    from your_db import Session, User
    
    db = Session()
    try:
        # Создание пользователя
        user = User(
            email=user_data['email'],
            name=f"{user_data['first_name']} {user_data['last_name']}",
            hashed_password=user_data['password_hash'],  # Уже хеширован!
            role=user_data['role'],
            is_active=user_data.get('is_active', True)
        )
        db.add(user)
        db.commit()
        
        logger.info(f"✅ User created: {user.email} (ID: {user.id})")
    except Exception as e:
        logger.error(f"❌ Error creating user: {e}")
        db.rollback()
    finally:
        db.close()
```

---

## 🧪 Шаг 4: Тестирование

### 4.1. Проверка подключения

```python
import pika

RABBITMQ_URL = "amqp://auth:PASSWORD@185.129.48.238:5672/"

try:
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    print("✅ Connected!")
    connection.close()
except Exception as e:
    print(f"❌ Error: {e}")
```

### 4.2. Отправка тестового события

Используйте скрипт `send_test_event.py` (создан ранее) или создайте пользователя через Central Auth Frontend.

### 4.3. Проверка логов

Ваше приложение должно вывести:

```
✅ Connected to RabbitMQ: user_events
📥 Listening for events: user.created, user.updated, user.deleted
🚀 Starting to consume messages...
📨 Received: user.created for test@example.com
✅ User created: test@example.com (ID: 1)
```

---

## 🔍 Шаг 5: Мониторинг

### RabbitMQ Management UI

**URL:** http://185.129.48.238:15672  
**Login:** `auth`  
**Password:** `NXsgvjB5Ff3VWHiKra1Boc3YIoXWAQYE2FBAikXNGg4=`

Что смотреть:
- **Queues** → Ваша очередь `{service}_user_events`
- **Messages** → Количество необработанных сообщений
- **Consumers** → Должен быть активный consumer (ваше приложение)
- **Connections** → Активные подключения

### Проверка на сервере

```bash
# Список очередей
docker exec auth-rabbitmq-prod rabbitmqctl list_queues name messages consumers

# Список подключений
docker exec auth-rabbitmq-prod rabbitmqctl list_connections user peer_host

# Список bindings
docker exec auth-rabbitmq-prod rabbitmqctl list_bindings | grep user_events
```

---

## 🚨 Важные моменты

### 1. Пароли уже захешированы
```python
# ❌ НЕ ДЕЛАЙТЕ ТАК:
user.password_hash = bcrypt.hash(user_data['password_hash'])

# ✅ ПРАВИЛЬНО:
user.password_hash = user_data['password_hash']  # Уже готов!
```

### 2. Проверяйте доступ для студентов
```python
# Студенты БЕЗ доступа к вашему сервису НЕ должны создаваться
if role == 'student' and service_name not in allowed_services:
    return  # Пропускаем
```

### 3. Мягкое удаление
```python
# ❌ НЕ удаляйте физически:
db.delete(user)

# ✅ Деактивируйте:
user.is_active = False
db.commit()
```

### 4. Идемпотентность
```python
# Обработка повторных событий должна быть безопасной
existing_user = db.query(User).filter_by(email=email).first()
if existing_user:
    # Обновляем вместо создания
    existing_user.name = new_name
else:
    # Создаем
    db.add(new_user)
```

---

## 🐛 Troubleshooting

### Проблема: "Connection refused"
**Решение:** Проверьте доступность порта:
```bash
nc -zv 185.129.48.238 5672
```

### Проблема: "ACCESS_REFUSED"
**Решение:** Проверьте credentials. Пользователь должен быть `auth`, не `guest`.

### Проблема: "Consumer не получает сообщения"
**Решение:** 
1. Проверьте что exchange и queue созданы
2. Проверьте bindings в Management UI
3. Убедитесь что consumer запущен и не упал

### Проблема: "Дубликаты пользователей"
**Решение:** Используйте `email` как уникальный идентификатор:
```python
user = db.query(User).filter_by(email=email).first()
if not user:
    user = User(email=email, ...)
    db.add(user)
```

---

## 📚 Дополнительные ресурсы

- **RabbitMQ Tutorial:** https://www.rabbitmq.com/tutorials/tutorial-one-python.html
- **Pika Documentation:** https://pika.readthedocs.io/
- **Exchange Types:** https://www.rabbitmq.com/tutorials/amqp-concepts.html

---

## 🎯 Checklist для внедрения

- [ ] Установлена библиотека `pika` (или аналог для вашего языка)
- [ ] Добавлены переменные `RABBITMQ_URL` и `RABBITMQ_EXCHANGE` в `.env`
- [ ] Создан consumer class с обработкой 3 событий
- [ ] Реализована проверка `allowed_services_json` для студентов
- [ ] Consumer запускается при старте приложения в фоновом потоке
- [ ] Протестирован на тестовых событиях
- [ ] Добавлено логирование всех операций
- [ ] Настроен мониторинг в RabbitMQ Management UI
- [ ] Документирована интеграция для команды

---

## ✨ Готово!

Теперь ваш сервис автоматически синхронизируется с **Central Auth System**! 

При создании/обновлении пользователей в Central Auth они мгновенно появляются/обновляются в вашем сервисе. 🚀

**Вопросы?** Проверьте документацию в `/lms/backend/RABBITMQ_INTEGRATION.md`
