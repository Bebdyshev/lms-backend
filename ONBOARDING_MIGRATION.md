# Миграция для отслеживания онбординга

## Описание
Добавлены поля `onboarding_completed` и `onboarding_completed_at` в таблицу `users` для отслеживания завершения онбординга пользователями.

## Локальное применение миграции

### Вариант 1: Использование скрипта migrate.sh
```bash
cd /Users/bebdyshev/Documents/Github/lms/backend
./migrate.sh
```

### Вариант 2: Прямая команда с переменной окружения
```bash
cd /Users/bebdyshev/Documents/Github/lms/backend
POSTGRES_URL="postgresql://myuser:mypassword@localhost:5432/lms_db" alembic upgrade head
```

### Вариант 3: Загрузка .env и запуск
```bash
cd /Users/bebdyshev/Documents/Github/lms/backend
export $(cat .env | grep -v '^#' | xargs)
alembic upgrade head
```

## Применение на продакшене

### Через Docker
```bash
# SSH на сервер
ssh user@your-server

# Перейти в директорию с проектом
cd /path/to/lms/backend

# Применить миграцию через Docker контейнер
docker-compose exec backend alembic upgrade head
```

### Альтернативный вариант (если контейнер не запущен)
```bash
# Запустить временный контейнер для миграции
docker-compose run --rm backend alembic upgrade head
```

## Проверка применения миграции

### Проверить текущую версию базы данных
```bash
# Локально
POSTGRES_URL="postgresql://myuser:mypassword@localhost:5432/lms_db" alembic current

# На продакшене
docker-compose exec backend alembic current
```

### Проверить наличие колонок в таблице
```bash
# Локально
docker exec postgres-lms psql -U myuser -d lms_db -c "\d users" | grep onboarding

# На продакшене
docker-compose exec postgres psql -U myuser -d lms_db -c "\d users" | grep onboarding
```

Должно вывести:
```
 onboarding_completed     | boolean                     |           | not null | false
 onboarding_completed_at  | timestamp without time zone |           |          |
```

## Откат миграции (если нужно)

```bash
# Локально
POSTGRES_URL="postgresql://myuser:mypassword@localhost:5432/lms_db" alembic downgrade -1

# На продакшене
docker-compose exec backend alembic downgrade -1
```

## История миграций

Чтобы увидеть все миграции:
```bash
POSTGRES_URL="postgresql://myuser:mypassword@localhost:5432/lms_db" alembic history
```

Текущая миграция: `57e19d19aae8` (add_onboarding_tracking_to_users)
Предыдущая: `86146539fee2` (add_enhanced_quiz_fields)

## Что изменилось

### Backend:
1. **models.py**: Добавлены поля в UserInDB:
   - `onboarding_completed: bool = False`
   - `onboarding_completed_at: Optional[datetime] = None`

2. **users.py**: Добавлен endpoint `POST /users/complete-onboarding`

3. **UserSchema**: Обновлена схема для включения новых полей

### Frontend:
1. **types/index.ts**: Добавлены поля в интерфейс User
2. **api.ts**: Добавлен метод `completeOnboarding()`
3. **OnboardingManager.tsx**: Интеграция с API для сохранения статуса
4. **AuthContext.tsx**: Поддержка обновления пользователя

## Тестирование

После применения миграции:

1. **Запустить backend:**
   ```bash
   cd backend
   source venv/bin/activate
   uvicorn src.app:app --reload
   ```

2. **Запустить frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

3. **Тестовый сценарий:**
   - Войти как новый пользователь (или сбросить онбординг кнопкой в dev mode)
   - Пройти приветственные экраны
   - Пройти тур (нажать "Next" на каждом шаге или "Skip" для пропуска)
   
4. **Проверить логи в консоли браузера:**
   ```
   [OnboardingManager] Starting onboarding flow...
   Welcome screens completed, starting tour...
   Starting tour: admin-onboarding (или другая роль)
   Tour steps: 6 (или другое количество)
   Step 1 (...): Found ✓
   ...
   [OnboardingTour] Tour closed, marking as complete
   Tour completed!
   Calling completeOnboarding API for user: <id>
   Onboarding API response: { ..., onboarding_completed: true, ... }
   [AuthContext] updateUser called with: { onboarding_completed: true, ... }
   Onboarding saved to localStorage
   ```

5. **Проверить сохранение:**
   - Перезагрузить страницу (F5)
   - Онбординг НЕ должен показаться снова
   - В логах должно быть: `[OnboardingManager] Onboarding already completed, skipping...`

6. **Проверить в базе данных:**
   ```bash
   # Локально
   docker exec postgres-lms psql -U myuser -d lms_db -c "SELECT id, email, onboarding_completed, onboarding_completed_at FROM users WHERE email='test@example.com';"
   ```

   Должно показать:
   ```
    id |       email        | onboarding_completed |   onboarding_completed_at   
   ----+--------------------+----------------------+-----------------------------
     1 | test@example.com   | t                    | 2025-10-27 12:34:56.789012
   ```

## Известные события NextStep.js

Компонент `OnboardingTour` слушает следующие события:
- `nextstep:complete` - тур завершен успешно (последний шаг пройден)
- `nextstep:end` - тур завершен
- `nextstep:skip` - тур пропущен пользователем
- Также отслеживается закрытие тура через `isNextStepVisible`

## Отладка

Если онбординг не сохраняется:

1. **Проверьте консоль браузера** - должны быть все логи выше
2. **Проверьте Network tab** - должен быть запрос `POST /users/complete-onboarding` со статусом 200
3. **Проверьте Response** - должен содержать `onboarding_completed: true`
4. **Проверьте localStorage** - должен быть ключ `onboarding_completed_<user_id>` со значением `"true"`
5. **Проверьте базу данных** - колонка должна быть обновлена
