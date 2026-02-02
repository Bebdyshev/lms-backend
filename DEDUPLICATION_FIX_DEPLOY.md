# Event Deduplication Fix - Production Deployment Guide

## Проблема
Календарь показывает дублирующиеся события - "Planned" (из LessonSchedule) и "Online Class" (из recurring Events) для одного и того же времени.

## Решение
Исправление на уровне кода: добавление `_group_ids` к виртуальным событиям, чтобы дедупликация работала корректно.

## Файлы для обновления
1. `src/services/event_service.py` - добавление `_group_ids` к виртуальным событиям
2. `src/routes/events.py` - обновление логики дедупликации для использования `_group_ids`

---

## Вариант 1: Автоматический деплой (Рекомендуется)

### На продакшн сервере:

```bash
# 1. Перейти в директорию backend
cd /path/to/lms/backend

# 2. Запустить скрипт деплоя (с dry-run для проверки)
python3 scripts/deploy_deduplication_fix.py --dry-run

# 3. Если все ок, применить изменения
python3 scripts/deploy_deduplication_fix.py

# 4. Перезапустить бэкенд
docker-compose restart web
# ИЛИ для systemd:
# sudo systemctl restart lms-backend

# 5. Проверить что все работает
python3 scripts/verify_deduplication_fix.py
```

### Откат в случае проблем:
```bash
# Автоматически созданный бэкап находится в:
ls -la backups/deduplication_fix_*

# Откатить изменения:
BACKUP_DIR="backups/deduplication_fix_YYYYMMDD_HHMMSS"
cp $BACKUP_DIR/event_service.py src/services/
cp $BACKUP_DIR/events.py src/routes/
docker-compose restart web
```

---

## Вариант 2: Bash скрипт

```bash
# На продакшн сервере
cd /path/to/lms/backend

# Запустить bash скрипт
./scripts/fix_event_deduplication.sh

# Перезапустить
docker-compose restart web
```

---

## Вариант 3: Ручное обновление

### Шаг 1: Создать бэкап
```bash
cd /path/to/lms/backend
mkdir -p backups/manual_$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/manual_$(date +%Y%m%d_%H%M%S)"
cp src/services/event_service.py $BACKUP_DIR/
cp src/routes/events.py $BACKUP_DIR/
```

### Шаг 2: Скопировать файлы с локальной машины
```bash
# На локальной машине (где все уже исправлено)
cd /Users/bebdyshev/Documents/Github/lms/backend

# Скопировать на сервер
scp src/services/event_service.py user@server:/path/to/lms/backend/src/services/
scp src/routes/events.py user@server:/path/to/lms/backend/src/routes/
```

### Шаг 3: Перезапустить на сервере
```bash
# На сервере
cd /path/to/lms/backend
docker-compose restart web

# Проверить логи
docker-compose logs -f web
```

---

## Проверка что исправление работает

### Способ 1: Скрипт верификации
```bash
python3 scripts/verify_deduplication_fix.py
```

### Способ 2: Ручная проверка
```bash
# Запустить Python в venv
source venv/bin/activate
python3

# В Python shell:
from datetime import datetime, timedelta
from src.config import SessionLocal
from src.services.event_service import EventService

db = SessionLocal()

# Получить виртуальные события
events = EventService.expand_recurring_events(
    db=db,
    start_date=datetime(2026, 2, 1),
    end_date=datetime(2026, 2, 28),
    group_ids=[27],  # ID вашей группы
    course_ids=[]
)

# Проверить что у событий есть _group_ids
for e in events[:3]:
    print(f"Event: {e.title}, _group_ids: {getattr(e, '_group_ids', None)}")

# Все события должны иметь _group_ids=[27]
db.close()
```

### Способ 3: Проверка через API
```bash
# Получить события календаря
curl -X GET "http://your-server:8000/events/calendar?year=2026&month=2" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  | jq '.[] | {title, start_datetime, groups}'

# Должны увидеть события без дубликатов
```

---

## Что изменилось в коде

### event_service.py
```python
# Добавлено перед циклом:
parent_group_ids = [eg.group_id for eg in parent.event_groups] if parent.event_groups else []

# Добавлено после создания virtual_event:
virtual_event._group_ids = parent_group_ids
```

### events.py
```python
# Обновлена дедупликация:
virtual_gids = getattr(e, '_group_ids', None)
e_group_ids = virtual_gids or ([eg.group_id for eg in e.event_groups] if hasattr(e, 'event_groups') else [])

# Обновлено получение group_names:
virtual_group_ids = getattr(event, '_group_ids', None)
if virtual_group_ids:
    groups = db.query(Group).filter(Group.id.in_(virtual_group_ids)).all()
    group_names = [g.name for g in groups]
    event_data.group_ids = virtual_group_ids
else:
    group_names = [eg.group.name for eg in event.event_groups if eg.group]
    event_data.group_ids = [eg.group_id for eg in event.event_groups]
```

---

## Ожидаемый результат

✅ Календарь показывает только одно событие для каждого таймслота
✅ Дубликаты "Planned" и "Online Class" исчезли
✅ События правильно отображаются с названиями групп
✅ Все тесты в verify_deduplication_fix.py проходят

---

## Мониторинг после деплоя

```bash
# Проверить логи бэкенда
docker-compose logs -f web | grep -i "event\|calendar"

# Проверить количество событий в календаре
# (должно быть меньше чем раньше из-за дедупликации)

# Проверить что нет ошибок 500
docker-compose logs web | grep "ERROR\|500"
```

---

## Контакты для поддержки
- Автор исправления: GitHub Copilot
- Дата: 2026-02-02
- Версия: 1.0
