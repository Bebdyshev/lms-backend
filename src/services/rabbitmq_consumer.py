"""
RabbitMQ Consumer для синхронизации пользователей из Central Auth Service
"""
import json
import logging
import os
import pika
import threading
from typing import Dict, Any
from sqlalchemy.orm import Session
from src.schemas.models import UserInDB
from src.config import SessionLocal
from passlib.context import CryptContext

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class RabbitMQConsumer:
    """Consumer для обработки событий пользователей из RabbitMQ"""
    
    def __init__(self, rabbitmq_url: str, exchange: str):
        self.rabbitmq_url = rabbitmq_url
        self.exchange = exchange
        self.connection = None
        self.channel = None
        self._running = False
        
    def connect(self):
        """Подключение к RabbitMQ"""
        try:
            # Устанавливаем соединение
            parameters = pika.URLParameters(self.rabbitmq_url)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Объявляем exchange (если еще не существует)
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type='topic',
                durable=True
            )
            
            # Создаем уникальную очередь для LMS
            result = self.channel.queue_declare(queue='lms_user_events', durable=True)
            queue_name = result.method.queue
            
            # Привязываем очередь к exchange с routing keys
            routing_keys = ['user.created', 'user.updated', 'user.deleted']
            for routing_key in routing_keys:
                self.channel.queue_bind(
                    exchange=self.exchange,
                    queue=queue_name,
                    routing_key=routing_key
                )
            
            logger.info(f"✅ Connected to RabbitMQ: {self.exchange}")
            logger.info(f"📥 Listening for events: {', '.join(routing_keys)}")
            
            return queue_name
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to RabbitMQ: {e}")
            raise
    
    def _handle_user_created(self, user_data: Dict[str, Any], db: Session):
        """Обработка события создания пользователя"""
        try:
            # Проверяем, есть ли уже пользователь с таким email
            existing_user = db.query(UserInDB).filter(
                UserInDB.email == user_data.get('email')
            ).first()
            
            if existing_user:
                logger.warning(f"⚠️  User already exists: {user_data.get('email')}")
                return
            
            # Проверяем, есть ли у пользователя доступ к LMS
            allowed_services = user_data.get('allowed_services_json', '[]')
            if isinstance(allowed_services, str):
                allowed_services = json.loads(allowed_services)
            
            # Для не-студентов разрешаем все, для студентов проверяем permissions
            role = user_data.get('role', 'student')
            if role != 'student' or 'lms' in allowed_services:
                # Создаем нового пользователя в LMS
                first_name = user_data.get('first_name', '')
                last_name = user_data.get('last_name', '')
                full_name = f"{first_name} {last_name}".strip()
                
                new_user = UserInDB(
                    email=user_data.get('email'),
                    name=full_name or user_data.get('email').split('@')[0],
                    hashed_password=user_data.get('password_hash', ''),  # Уже хеширован
                    role=role,
                    is_active=user_data.get('is_active', True),
                    student_id=user_data.get('id')  # Сохраняем ID из central-auth
                )
                
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                
                logger.info(f"✅ User created in LMS: {new_user.email} (ID: {new_user.id})")
            else:
                logger.info(f"⏭️  Skipping user {user_data.get('email')} - no LMS access")
                
        except Exception as e:
            logger.error(f"❌ Error handling user.created: {e}")
            db.rollback()
            raise
    
    def _handle_user_updated(self, user_data: Dict[str, Any], db: Session):
        """Обработка события обновления пользователя"""
        try:
            # Ищем пользователя по email
            user = db.query(UserInDB).filter(
                UserInDB.email == user_data.get('email')
            ).first()
            
            if not user:
                logger.warning(f"⚠️  User not found for update: {user_data.get('email')}")
                # Если пользователь не найден, создаем его
                self._handle_user_created(user_data, db)
                return
            
            # Проверяем доступ к LMS
            allowed_services = user_data.get('allowed_services_json', '[]')
            if isinstance(allowed_services, str):
                allowed_services = json.loads(allowed_services)
            
            role = user_data.get('role', 'student')
            
            # Если это студент без доступа к LMS - деактивируем
            if role == 'student' and 'lms' not in allowed_services:
                user.is_active = False
                logger.info(f"🔒 User deactivated (no LMS access): {user.email}")
            else:
                # Обновляем данные пользователя
                first_name = user_data.get('first_name', '')
                last_name = user_data.get('last_name', '')
                full_name = f"{first_name} {last_name}".strip()
                
                if full_name:
                    user.name = full_name
                user.role = role
                user.is_active = user_data.get('is_active', True)
                
                # Обновляем пароль если он изменился
                if user_data.get('password_hash'):
                    user.hashed_password = user_data.get('password_hash')
                
                logger.info(f"✅ User updated in LMS: {user.email}")
            
            db.commit()
            
        except Exception as e:
            logger.error(f"❌ Error handling user.updated: {e}")
            db.rollback()
            raise
    
    def _handle_user_deleted(self, user_data: Dict[str, Any], db: Session):
        """Обработка события удаления пользователя"""
        try:
            # Ищем пользователя по email
            user = db.query(UserInDB).filter(
                UserInDB.email == user_data.get('email')
            ).first()
            
            if not user:
                logger.warning(f"⚠️  User not found for deletion: {user_data.get('email')}")
                return
            
            # Мягкое удаление - деактивируем пользователя
            user.is_active = False
            db.commit()
            
            logger.info(f"🗑️  User deactivated in LMS: {user.email}")
            
        except Exception as e:
            logger.error(f"❌ Error handling user.deleted: {e}")
            db.rollback()
            raise
    
    def _process_message(self, ch, method, properties, body):
        """Обработка входящего сообщения из RabbitMQ"""
        db = SessionLocal()
        try:
            # Парсим JSON сообщение
            message = json.loads(body)
            event_type = message.get('event_type')
            user_data = message.get('user', {})
            
            logger.info(f"📨 Received event: {event_type} for user: {user_data.get('email')}")
            
            # Обрабатываем событие в зависимости от типа
            if event_type == 'user.created':
                self._handle_user_created(user_data, db)
            elif event_type == 'user.updated':
                self._handle_user_updated(user_data, db)
            elif event_type == 'user.deleted':
                self._handle_user_deleted(user_data, db)
            else:
                logger.warning(f"⚠️  Unknown event type: {event_type}")
            
            # Подтверждаем обработку сообщения
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}")
            # Отклоняем сообщение и возвращаем в очередь
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        finally:
            db.close()
    
    def start_consuming(self):
        """Запуск потребления сообщений"""
        try:
            queue_name = self.connect()
            
            # Настраиваем QoS - обрабатываем по одному сообщению за раз
            self.channel.basic_qos(prefetch_count=1)
            
            # Начинаем потреблять сообщения
            self.channel.basic_consume(
                queue=queue_name,
                on_message_callback=self._process_message
            )
            
            self._running = True
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            logger.error(f"❌ Consumer error: {e}")
            raise
    
    def stop(self):
        """Остановка consumer"""
        self._running = False
        if self.channel:
            self.channel.stop_consuming()
        if self.connection:
            self.connection.close()
        logger.info("✅ Consumer stopped")


def start_rabbitmq_consumer_thread():
    """Запуск RabbitMQ consumer в отдельном потоке"""
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
    exchange = os.getenv('RABBITMQ_EXCHANGE', 'user_events')
    
    consumer = RabbitMQConsumer(rabbitmq_url, exchange)
    
    def run_consumer():
        try:
            consumer.start_consuming()
        except Exception as e:
            logger.error(f"❌ RabbitMQ consumer thread error: {e}")
    
    # Запускаем consumer в daemon потоке
    thread = threading.Thread(target=run_consumer, daemon=True)
    thread.start()
    logger.info("🧵 RabbitMQ consumer thread started")
    
    return consumer
