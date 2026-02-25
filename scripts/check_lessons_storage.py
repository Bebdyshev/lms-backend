#!/usr/bin/env python3
"""
Check where lessons are stored: events vs lesson_schedules.
Run from backend dir: python scripts/check_lessons_storage.py
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from src.config import SessionLocal
from src.models import Event, EventGroup, LessonSchedule, Group


def main():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("LESSONS STORAGE CHECK: events vs lesson_schedules")
        print("=" * 70)

        # --- EVENTS (event_type='class') ---
        events_class = db.query(Event).filter(
            Event.event_type == "class"
        ).all()
        events_active = [e for e in events_class if e.is_active]
        events_inactive = [e for e in events_class if not e.is_active]

        print("\n--- EVENTS (event_type='class') ---")
        print(f"  Total:     {len(events_class)}")
        print(f"  Active:    {len(events_active)}")
        print(f"  Inactive:  {len(events_inactive)}")

        if events_class:
            # Get group names for events
            event_ids = [e.id for e in events_class[:5]]
            event_groups = db.query(EventGroup).filter(
                EventGroup.event_id.in_(event_ids)
            ).all()
            eg_map = {eg.event_id: eg.group_id for eg in event_groups}
            groups = {g.id: g.name for g in db.query(Group).filter(Group.id.in_(eg_map.values())).all()}

            print("\n  Sample (first 5):")
            for e in events_class[:5]:
                gid = eg_map.get(e.id)
                gname = groups.get(gid, "?") if gid else "?"
                print(f"    id={e.id} | {e.title[:50]}... | teacher_id={e.teacher_id} | "
                      f"group={gname} | {e.start_datetime.strftime('%Y-%m-%d %H:%M')} | active={e.is_active}")

        # --- LESSON_SCHEDULES ---
        all_schedules = db.query(LessonSchedule).all()
        schedules_active = [s for s in all_schedules if s.is_active]
        schedules_inactive = [s for s in all_schedules if not s.is_active]

        print("\n--- LESSON_SCHEDULES ---")
        print(f"  Total:     {len(all_schedules)}")
        print(f"  Active:    {len(schedules_active)}")
        print(f"  Inactive:  {len(schedules_inactive)}")

        if all_schedules:
            group_ids = list(set(s.group_id for s in all_schedules[:5]))
            groups = {g.id: g.name for g in db.query(Group).filter(Group.id.in_(group_ids)).all()}
            print("\n  Sample (first 5):")
            for s in all_schedules[:5]:
                gname = groups.get(s.group_id, "?")
                print(f"    id={s.id} | group={gname} | lesson_id={s.lesson_id} | "
                      f"{s.scheduled_at.strftime('%Y-%m-%d %H:%M')} | week={s.week_number} | active={s.is_active}")

        # --- SUMMARY ---
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        if len(events_active) > 0 and len(schedules_active) == 0:
            print("  -> Lessons are stored in EVENTS (Schedule Generator flow)")
        elif len(events_active) == 0 and len(schedules_active) > 0:
            print("  -> Lessons are stored in LESSON_SCHEDULES (legacy flow)")
        elif len(events_active) > 0 and len(schedules_active) > 0:
            print("  -> BOTH: Events and LessonSchedules have data (mixed)")
        else:
            print("  -> No lesson data found in either table")
        print("=" * 70)

    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
