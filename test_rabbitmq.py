#!/usr/bin/env python3
"""
Тестовый скрипт для проверки RabbitMQ интеграции
Публикует тестовые события в RabbitMQ для проверки работы consumer'а
"""

import json
import pika
import uuid
from datetime import datetime
import sys

RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"
EXCHANGE = "user_events"


def publish_event(routing_key: str, event_data: dict):
    """Публикация события в RabbitMQ"""
    try:
        # Подключение к RabbitMQ
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()
        
        # Объявляем exchange
        channel.exchange_declare(
            exchange=EXCHANGE,
            exchange_type='topic',
            durable=True
        )
        
        # Публикуем сообщение
        message = json.dumps(event_data)
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=message,
            properties=pika.BasicProperties(
                content_type='application/json',
                delivery_mode=2  # persistent
            )
        )
        
        print(f"✅ Published event: {routing_key}")
        print(f"📦 Message: {json.dumps(event_data, indent=2)}")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ Error publishing event: {e}")
        return False


def test_user_created():
    """Тест создания пользователя"""
    print("\n" + "="*60)
    print("🧪 TEST 1: User Created Event")
    print("="*60)
    
    event = {
        "event_type": "user.created",
        "user_id": str(uuid.uuid4()),
        "user": {
            "id": str(uuid.uuid4()),
            "email": f"test.student.{datetime.now().timestamp()}@example.com",
            "first_name": "Тест",
            "last_name": "Студентов",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIqKW0zQvO",
            "role": "student",
            "is_active": True,
            "allowed_services_json": '["lms", "sat"]'
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return publish_event("user.created", event)


def test_user_updated():
    """Тест обновления пользователя"""
    print("\n" + "="*60)
    print("🧪 TEST 2: User Updated Event")
    print("="*60)
    
    event = {
        "event_type": "user.updated",
        "user_id": str(uuid.uuid4()),
        "user": {
            "id": str(uuid.uuid4()),
            "email": "existing.student@example.com",
            "first_name": "Обновленный",
            "last_name": "Пользователь",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIqKW0zQvO",
            "role": "student",
            "is_active": True,
            "allowed_services_json": '["lms"]'
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return publish_event("user.updated", event)


def test_user_no_lms_access():
    """Тест пользователя БЕЗ доступа к LMS"""
    print("\n" + "="*60)
    print("🧪 TEST 3: User Without LMS Access")
    print("="*60)
    
    event = {
        "event_type": "user.created",
        "user_id": str(uuid.uuid4()),
        "user": {
            "id": str(uuid.uuid4()),
            "email": f"no.lms.{datetime.now().timestamp()}@example.com",
            "first_name": "Без",
            "last_name": "ЛМС",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIqKW0zQvO",
            "role": "student",
            "is_active": True,
            "allowed_services_json": '["sat", "ielts"]'  # НЕТ lms
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return publish_event("user.created", event)


def test_teacher_created():
    """Тест создания преподавателя (всегда имеет доступ)"""
    print("\n" + "="*60)
    print("🧪 TEST 4: Teacher Created (Full Access)")
    print("="*60)
    
    event = {
        "event_type": "user.created",
        "user_id": str(uuid.uuid4()),
        "user": {
            "id": str(uuid.uuid4()),
            "email": f"teacher.{datetime.now().timestamp()}@example.com",
            "first_name": "Учитель",
            "last_name": "Иванов",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIqKW0zQvO",
            "role": "teacher",
            "is_active": True,
            "allowed_services_json": '[]'  # Пустой, но доступ будет
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return publish_event("user.created", event)


def test_user_deleted():
    """Тест удаления пользователя"""
    print("\n" + "="*60)
    print("🧪 TEST 5: User Deleted Event")
    print("="*60)
    
    event = {
        "event_type": "user.deleted",
        "user_id": str(uuid.uuid4()),
        "user": {
            "id": str(uuid.uuid4()),
            "email": "to.delete@example.com",
            "first_name": "Удаляемый",
            "last_name": "Пользователь",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIqKW0zQvO",
            "role": "student",
            "is_active": False,
            "allowed_services_json": '["lms"]'
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return publish_event("user.deleted", event)


def main():
    """Запуск всех тестов"""
    print("\n" + "🐰 RabbitMQ Integration Test Suite")
    print("="*60)
    print(f"📡 RabbitMQ URL: {RABBITMQ_URL}")
    print(f"📮 Exchange: {EXCHANGE}")
    print("="*60)
    
    tests = [
        ("User Created", test_user_created),
        ("User Updated", test_user_updated),
        ("User Without LMS Access", test_user_no_lms_access),
        ("Teacher Created", test_teacher_created),
        ("User Deleted", test_user_deleted),
    ]
    
    results = []
    for test_name, test_func in tests:
        success = test_func()
        results.append((test_name, success))
    
    # Итоговый отчет
    print("\n" + "="*60)
    print("📊 TEST RESULTS")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print("="*60)
    print(f"Total: {passed}/{total} tests passed")
    print("="*60)
    
    print("\n💡 Next steps:")
    print("1. Check LMS backend logs for consumer output")
    print("2. Check RabbitMQ Management UI: http://localhost:15672")
    print("3. Verify users were created/updated in LMS database")
    
    return passed == total


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        sys.exit(1)
