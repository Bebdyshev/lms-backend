import sys
import os
from datetime import datetime, timedelta

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.config import SessionLocal
from src.schemas.models import Event, EventGroup, Group

def debug_group(group_id, week_number=1):
    db = SessionLocal()
    try:
        print(f"\n--- Debugging Group {group_id} Week {week_number} ---")
        
        # 1. Check if group exists
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            print("Group not found!")
            return

        print(f"Group: {group.name} (ID: {group.id})")

        # 2. Find first event
        first_event = db.query(Event).join(EventGroup).filter(
            EventGroup.group_id == group_id,
            Event.event_type == 'class',
            Event.is_active == True
        ).order_by(Event.start_datetime.asc()).first()

        if not first_event:
            print("No 'class' events found for this group!")
            # Check if any events exist
            any_event = db.query(Event).join(EventGroup).filter(
                EventGroup.group_id == group_id
            ).first()
            if any_event:
                print(f"Found non-class event: {any_event.title} ({any_event.event_type})")
                print("No events at all for this group.")
            # Continue to check legacy
            # return  <-- Removed

            # Continue to check legacy
            # return  <-- Removed

        if first_event:
            print(f"First Event: {first_event.title} at {first_event.start_datetime}")
            
            start_of_week1 = first_event.start_datetime.date()
            start_of_week1 = start_of_week1 - timedelta(days=start_of_week1.weekday())
            print(f"Week 1 Start (Monday): {start_of_week1}")

            week_start_date = start_of_week1 + timedelta(weeks=week_number - 1)
            week_end_date = week_start_date + timedelta(days=7)
            print(f"Requested Week {week_number}: {week_start_date} to {week_end_date}")

            # 3. Find events in range
            events = db.query(Event).join(EventGroup).filter(
                EventGroup.group_id == group_id,
                Event.event_type == 'class',
                Event.is_active == True,
                Event.start_datetime >= datetime.combine(week_start_date, datetime.min.time()),
                Event.start_datetime < datetime.combine(week_end_date, datetime.min.time())
            ).order_by(Event.start_datetime).all()

            print(f"Events found in range: {len(events)}")
            for e in events:
                print(f" - {e.title} at {e.start_datetime}")

        # 4. Check for legacy schedules
        from src.schemas.models import LessonSchedule
        schedules = db.query(LessonSchedule).filter(
            LessonSchedule.group_id == group_id,
            LessonSchedule.is_active == True
        ).all()
        print(f"Legacy LessonSchedules found: {len(schedules)}")
        if schedules:
            print(f" - First schedule: {schedules[0].scheduled_at} (Week {schedules[0].week_number})")

    finally:
        db.close()

if __name__ == "__main__":
    debug_group(5)
    debug_group(7)
