
import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

# Add the parent directory to sys.path to allow importing from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import SessionLocal
from src.schemas.models import Event, EventGroup, Group

def debug_calendar():
    db = SessionLocal()
    try:
        print("=== Debugging Calendar Events ===")
        
        # 1. List all events
        print("\n1. All Events in DB:")
        events = db.query(Event).all()
        for e in events:
            print(f"ID: {e.id}, Title: {e.title}, Start: {e.start_datetime}, Recurring: {e.is_recurring}, Pattern: {e.recurrence_pattern}, EndDate: {e.recurrence_end_date}")
            groups = db.query(EventGroup).filter(EventGroup.event_id == e.id).all()
            print(f"   Groups: {[g.group_id for g in groups]}")

        # 2. Simulate get_calendar_events for Dec 2025
        print("\n2. Simulating get_calendar_events for Dec 2025")
        year = 2025
        month = 12
        start_date = datetime(year, month, 1)
        end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        print(f"Range: {start_date} to {end_date}")

        # Assume admin user (sees all groups)
        all_groups = db.query(Group).all()
        user_group_ids = [g.id for g in all_groups]
        print(f"User Group IDs: {user_group_ids}")

        # Query for recurring parents
        recurring_parents = db.query(Event).join(EventGroup).filter(
            EventGroup.group_id.in_(user_group_ids),
            Event.is_active == True,
            Event.is_recurring == True,
            Event.start_datetime <= end_date,
            or_(
                Event.recurrence_end_date == None,
                Event.recurrence_end_date >= start_date.date()
            )
        ).options(
            joinedload(Event.creator),
            joinedload(Event.event_groups).joinedload(EventGroup.group)
        ).all()
        
        print(f"Found {len(recurring_parents)} recurring parents")
        for p in recurring_parents:
            print(f"  Parent: {p.title} (ID: {p.id})")

        # Generate events
        generated_events = []
        import calendar as cal_module

        for parent in recurring_parents:
            current_start = parent.start_datetime
            current_end = parent.end_datetime
            duration = current_end - current_start
            original_start_day = parent.start_datetime.day
            
            print(f"  Generating for {parent.title} starting from {current_start}")
            
            while current_start <= end_date:
                if current_start >= start_date and current_start <= end_date:
                    print(f"    Generated instance: {current_start}")
                    generated_events.append(current_start)
                
                # Increment
                if parent.recurrence_pattern == "daily":
                    current_start += timedelta(days=1)
                elif parent.recurrence_pattern == "weekly":
                    current_start += timedelta(weeks=1)
                elif parent.recurrence_pattern == "biweekly":
                    current_start += timedelta(weeks=2)
                elif parent.recurrence_pattern == "monthly":
                    year = current_start.year + (current_start.month // 12)
                    month = (current_start.month % 12) + 1
                    day = min(original_start_day, cal_module.monthrange(year, month)[1])
                    current_start = current_start.replace(year=year, month=month, day=day)
                else:
                    break
                
                if parent.recurrence_end_date and current_start.date() > parent.recurrence_end_date:
                    break
        
        print(f"Total generated events: {len(generated_events)}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    debug_calendar()
