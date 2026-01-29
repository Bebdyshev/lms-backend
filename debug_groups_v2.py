from src.config import SessionLocal
from src.schemas.models import UserInDB, Group, GroupStudent, Event, EventGroup, LessonSchedule
from datetime import datetime, timedelta

def debug_group(group_id):
    db = SessionLocal()
    try:
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            print(f"Group {group_id} not found")
            return

        print(f"Group: {group.name} (ID: {group.id})")
        
        # Check LessonSchedules
        schedules = db.query(LessonSchedule).filter(
            LessonSchedule.group_id == group_id,
            LessonSchedule.is_active == True
        ).order_by(LessonSchedule.scheduled_at).all()
        
        print(f"Active LessonSchedules: {len(schedules)}")
        for s in schedules[:20]: # Show first 20
            print(f" - ID: {s.id} | Lesson: {s.lesson_id} | Time: {s.scheduled_at} | Week: {s.week_number}")
        
        if len(schedules) > 20:
            print(f" ... and {len(schedules) - 20} more")

        # Check for overlaps in schedules
        seen_times = {} # time -> [ids]
        for s in schedules:
            t = s.scheduled_at
            if t not in seen_times:
                seen_times[t] = []
            seen_times[t].append(s.id)
        
        overlaps = {t: ids for t, ids in seen_times.items() if len(ids) > 1}
        if overlaps:
            print(f"\nFound {len(overlaps)} overlapping schedule slots!")
            for t, ids in overlaps.items():
                print(f" - {t}: {ids}")
        else:
            print("\nNo overlapping schedule slots found.")

        # Check Events
        events = db.query(Event).join(EventGroup).filter(
            EventGroup.group_id == group_id,
            Event.is_active == True
        ).all()
        print(f"\nActive Events: {len(events)}")
        for e in events:
            print(f" - ID: {e.id} | Title: {e.title} | Time: {e.start_datetime} | Recurring: {e.is_recurring}")

    finally:
        db.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        debug_group(int(sys.argv[1]))
    else:
        print("Usage: python debug_groups_v2.py <group_id>")
