#!/usr/bin/env python3
"""
Скрипт для восстановления Unit 3 (Inequalities) из Math секции курса SAT из бэкапа
"""

import subprocess
import tempfile
import os
import sys

# Конфигурация
CONTAINER_NAME = "postgres-lms"
DB_NAME = "lms_db"
DB_USER = "myuser"
BACKUP_FILE = "/Users/bebdyshev/Documents/Github/lms/backend/backups/lms_db_20260109_095224.dump"
LESSON_ID = 9  # Unit 3: Inequalities
MODULE_ID = 2  # Math

def run_docker_psql(sql_command):
    """Выполнить SQL команду в Docker контейнере"""
    cmd = [
        "docker", "exec", "-t", CONTAINER_NAME,
        "psql", "-U", DB_USER, "-d", DB_NAME,
        "-c", sql_command
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout, result.stderr, result.returncode

def restore_from_backup():
    """Восстановить данные из бэкапа во временную базу данных"""
    print("🔄 Создаю временную базу данных для восстановления бэкапа...")
    
    temp_db = "temp_restore_db"
    
    # Удалить временную БД если существует
    run_docker_psql(f"DROP DATABASE IF EXISTS {temp_db};")
    
    # Создать временную БД
    stdout, stderr, code = run_docker_psql(f"CREATE DATABASE {temp_db};")
    if code != 0:
        print(f"❌ Ошибка создания временной БД: {stderr}")
        return None
    
    # Восстановить бэкап во временную БД
    print("🔄 Восстанавливаю бэкап во временную базу данных...")
    restore_cmd = [
        "docker", "exec", "-i", CONTAINER_NAME,
        "pg_restore", "-U", DB_USER, "-d", temp_db, "-v"
    ]
    
    with open(BACKUP_FILE, 'rb') as f:
        result = subprocess.run(restore_cmd, stdin=f, capture_output=True)
    
    if result.returncode != 0:
        print(f"⚠️  Предупреждения при восстановлении (обычно это нормально)")
    else:
        print("✅ Бэкап успешно восстановлен во временную БД")
    
    return temp_db

def get_lesson_data(temp_db):
    """Получить все связанные данные для урока из временной БД"""
    print(f"📚 Извлекаю данные для Unit 3 (lesson_id={LESSON_ID})...")
    
    # Получить ID всех связанных шагов
    steps_query = f"SELECT id FROM {temp_db}.public.steps WHERE lesson_id = {LESSON_ID};"
    stdout, _, _ = run_docker_psql(steps_query)
    
    # Парсим ID шагов из вывода
    step_ids = []
    for line in stdout.split('\n')[2:-2]:  # Пропускаем заголовок и футер
        line = line.strip()
        if line and line.isdigit():
            step_ids.append(int(line))
    
    print(f"   Найдено шагов: {len(step_ids)}")
    
    return {
        'lesson_id': LESSON_ID,
        'step_ids': step_ids
    }

def backup_current_data():
    """Создать бэкап текущих данных перед удалением"""
    print("💾 Создаю бэкап текущих данных Unit 3...")
    
    timestamp = subprocess.run(['date', '+%Y%m%d_%H%M%S'], capture_output=True, text=True).stdout.strip()
    backup_sql = f"/tmp/unit3_backup_{timestamp}.sql"
    
    # Экспортируем текущие данные
    export_cmd = [
        "docker", "exec", "-t", CONTAINER_NAME,
        "pg_dump", "-U", DB_USER, "-d", DB_NAME,
        "-t", "lessons", "-t", "steps", "-t", "step_attachments",
        "-t", "quiz_attempts", "-t", "progress",
        "--data-only",
        f"--file=/tmp/unit3_backup_{timestamp}.sql"
    ]
    
    subprocess.run(export_cmd)
    print(f"   Бэкап создан: {backup_sql}")

def delete_current_unit_data():
    """Удалить текущие данные Unit 3"""
    print(f"🗑️  Удаляю текущие данные Unit 3 (lesson_id={LESSON_ID})...")
    
    # Порядок удаления важен из-за foreign key constraints
    tables_to_clean = [
        ('quiz_attempts', 'step_id', 'step_id IN (SELECT id FROM steps WHERE lesson_id = {})'),
        ('progress', 'step_id', 'step_id IN (SELECT id FROM steps WHERE lesson_id = {})'),
        ('step_attachments', 'step_id', 'step_id IN (SELECT id FROM steps WHERE lesson_id = {})'),
        ('steps', 'lesson_id', 'lesson_id = {}'),
    ]
    
    for table, _, condition in tables_to_clean:
        sql = f"DELETE FROM {table} WHERE {condition.format(LESSON_ID)};"
        stdout, stderr, code = run_docker_psql(sql)
        if code != 0:
            print(f"   ⚠️  Ошибка при удалении из {table}: {stderr}")
        else:
            print(f"   ✅ Очищена таблица: {table}")

def copy_data_from_temp(temp_db, data):
    """Скопировать данные из временной БД в основную"""
    print(f"📥 Копирую данные из бэкапа в основную БД...")
    
    step_ids_str = ','.join(map(str, data['step_ids'])) if data['step_ids'] else '0'
    
    # Обновляем урок (lesson)
    sql = f"""
    INSERT INTO lessons (id, module_id, title, description, duration_minutes, order_index, created_at, next_lesson_id)
    SELECT id, module_id, title, description, duration_minutes, order_index, created_at, next_lesson_id
    FROM {temp_db}.public.lessons
    WHERE id = {LESSON_ID}
    ON CONFLICT (id) DO UPDATE SET
        title = EXCLUDED.title,
        description = EXCLUDED.description,
        duration_minutes = EXCLUDED.duration_minutes,
        order_index = EXCLUDED.order_index;
    """
    run_docker_psql(sql)
    print("   ✅ Урок обновлен")
    
    # Копируем шаги (steps)
    if data['step_ids']:
        sql = f"""
        INSERT INTO steps (id, lesson_id, step_type, title, content, video_url, order_index, duration_minutes, created_at)
        SELECT id, lesson_id, step_type, title, content, video_url, order_index, duration_minutes, created_at
        FROM {temp_db}.public.steps
        WHERE id IN ({step_ids_str})
        ON CONFLICT (id) DO UPDATE SET
            step_type = EXCLUDED.step_type,
            title = EXCLUDED.title,
            content = EXCLUDED.content,
            video_url = EXCLUDED.video_url,
            order_index = EXCLUDED.order_index,
            duration_minutes = EXCLUDED.duration_minutes;
        """
        run_docker_psql(sql)
        print(f"   ✅ Скопировано шагов: {len(data['step_ids'])}")
        
        # Копируем вложения шагов (step_attachments)
        sql = f"""
        INSERT INTO step_attachments (id, step_id, file_type, file_url, title, created_at)
        SELECT id, step_id, file_type, file_url, title, created_at
        FROM {temp_db}.public.step_attachments
        WHERE step_id IN ({step_ids_str})
        ON CONFLICT (id) DO UPDATE SET
            file_type = EXCLUDED.file_type,
            file_url = EXCLUDED.file_url,
            title = EXCLUDED.title;
        """
        run_docker_psql(sql)
        print("   ✅ Вложения шагов скопированы")

def cleanup_temp_db(temp_db):
    """Удалить временную БД"""
    print(f"🧹 Удаляю временную базу данных {temp_db}...")
    run_docker_psql(f"DROP DATABASE IF EXISTS {temp_db};")
    print("   ✅ Временная БД удалена")

def main():
    print("=" * 60)
    print("🎯 Восстановление Unit 3: Inequalities из Math секции SAT")
    print("=" * 60)
    
    if not os.path.exists(BACKUP_FILE):
        print(f"❌ Файл бэкапа не найден: {BACKUP_FILE}")
        sys.exit(1)
    
    print(f"\n📁 Файл бэкапа: {BACKUP_FILE}")
    print(f"📝 Lesson ID: {LESSON_ID} (Unit 3: Inequalities)")
    print(f"📚 Module ID: {MODULE_ID} (Math)\n")
    
    response = input("⚠️  ВНИМАНИЕ: Это удалит текущие данные Unit 3 и заменит их данными из бэкапа.\nПродолжить? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Отменено пользователем")
        sys.exit(0)
    
    try:
        # Шаг 1: Восстановить бэкап во временную БД
        temp_db = restore_from_backup()
        if not temp_db:
            sys.exit(1)
        
        # Шаг 2: Получить данные из временной БД
        data = get_lesson_data(temp_db)
        
        # Шаг 3: Создать бэкап текущих данных
        backup_current_data()
        
        # Шаг 4: Удалить текущие данные Unit 3
        delete_current_unit_data()
        
        # Шаг 5: Скопировать данные из временной БД
        copy_data_from_temp(temp_db, data)
        
        # Шаг 6: Очистить временную БД
        cleanup_temp_db(temp_db)
        
        print("\n" + "=" * 60)
        print("✅ УСПЕШНО! Unit 3 восстановлен из бэкапа")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
