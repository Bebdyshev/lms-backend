#!/usr/bin/env python3
"""
Миграция: конвертация Event и LessonSchedule из KZ (Asia/Almaty, UTC+5) в UTC.

Проблема: старый EventForm сохранял время как KZ local (напр. 20:00 KZ) без конвертации.
API возвращает с суффиксом Z (как UTC), фронтенд добавляет +5h → неправильное отображение.

Скрипт вычитает 5 часов из start_datetime, end_datetime (events) и scheduled_at (lesson_schedules),
предполагая что текущие значения — KZ local time.

ВНИМАНИЕ: Если данные уже в UTC (bulk schedule, новый EventForm), НЕ запускайте — испортит время.

Запуск из backend/:
  python scripts/migrate_events_kz_to_utc.py --dry-run      # только показать изменения
  python scripts/migrate_events_kz_to_utc.py --execute      # применить KZ->UTC
  python scripts/migrate_events_kz_to_utc.py --execute --reverse  # откат (UTC->KZ, +5h)
"""
import argparse
import sys
from pathlib import Path
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import SessionLocal
from src.events.models import Event, LessonSchedule

KZ_OFFSET = timedelta(hours=5)


def kz_to_utc(dt):
    """Считаем dt как KZ local, возвращаем naive UTC."""
    return dt - KZ_OFFSET


def utc_to_kz(dt):
    """Откат: считаем dt как UTC, возвращаем KZ local (naive)."""
    return dt + KZ_OFFSET


def main():
    parser = argparse.ArgumentParser(description="Migrate events from KZ to UTC")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    parser.add_argument("--execute", action="store_true", help="Apply migration")
    parser.add_argument("--reverse", action="store_true", help="Reverse: UTC->KZ (+5h), for rollback")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Укажите --dry-run или --execute")
        sys.exit(1)

    convert_fn = utc_to_kz if args.reverse else kz_to_utc
    direction = "UTC->KZ (откат)" if args.reverse else "KZ->UTC"
    print(f"\nРежим: {direction}")

    db = SessionLocal()
    try:
        # --- Events ---
        events = db.query(Event).all()
        print(f"\n=== EVENTS: {len(events)} записей ===")
        updated_events = 0
        for e in events:
            new_start = convert_fn(e.start_datetime)
            new_end = convert_fn(e.end_datetime)
            if e.start_datetime != new_start or e.end_datetime != new_end:
                updated_events += 1
                print(f"  id={e.id} | {e.title[:40]}...")
                print(f"    start: {e.start_datetime} -> {new_start}")
                print(f"    end:   {e.end_datetime} -> {new_end}")
                if args.execute:
                    e.start_datetime = new_start
                    e.end_datetime = new_end
        print(f"  Обновлено: {updated_events}")

        # --- LessonSchedules ---
        schedules = db.query(LessonSchedule).all()
        print(f"\n=== LESSON_SCHEDULES: {len(schedules)} записей ===")
        updated_sched = 0
        for s in schedules:
            new_at = convert_fn(s.scheduled_at)
            if s.scheduled_at != new_at:
                updated_sched += 1
                print(f"  id={s.id} | group_id={s.group_id} | {s.scheduled_at} -> {new_at}")
                if args.execute:
                    s.scheduled_at = new_at
        print(f"  Обновлено: {updated_sched}")

        if args.execute and (updated_events > 0 or updated_sched > 0):
            db.commit()
            print("\n✓ Миграция применена.")
        elif args.dry_run:
            print("\n(режим --dry-run, изменения не применены)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
