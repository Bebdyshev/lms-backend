
import sys
import os
from datetime import datetime, timedelta, time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add current directory to path to allow imports
sys.path.append(os.getcwd())

from src.schemas.models import Group, LessonSchedule, GroupAssignment, Event, EventGroup
from dotenv import load_dotenv
load_dotenv()

POSTGRES_URL = os.getenv("POSTGRES_URL")

def switch_to_recurring_events():
    if not POSTGRES_URL:
        print("Error: POSTGRES_URL not found in environment.")
        return

    engine = create_engine(POSTGRES_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # 1. Find Group
        group_name = "Intensive 1"
        group = db.query(Group).filter(Group.name.ilike(f"%{group_name}%")).first()
        
        if not group:
            print(f"Group '{group_name}' not found.")
            return
            
        print(f"Switching schedule for: {group.name} (ID: {group.id})")
        
        # 2. Deactivate Old LessonSchedules
        old_schedules = db.query(LessonSchedule).filter(
            LessonSchedule.group_id == group.id,
            LessonSchedule.is_active == True
        ).all()
        
        print(f"Deactivating {len(old_schedules)} LessonSchedule items tied to Course Units...")
        for s in old_schedules:
            s.is_active = False
            # Also deactivate GroupAssignments linked to these
            gas = db.query(GroupAssignment).filter(
                GroupAssignment.lesson_schedule_id == s.id,
                GroupAssignment.is_active == True
            ).all()
            for ga in gas:
                ga.is_active = False
        
        db.flush()
        
        # 2.5 Clean up existing "Online Class" recurring events (to avoid duplicates on re-run)
        existing_recurring = db.query(Event).join(EventGroup).filter(
            EventGroup.group_id == group.id,
            Event.title == "Online Class", # Target specifically the generic ones we create
            Event.is_recurring == True,
            Event.is_active == True
        ).all()
        
        print(f"Deactivating {len(existing_recurring)} existing 'Online Class' event series to prevent duplicates...")
        for e in existing_recurring:
            e.is_active = False
            
        db.flush()
        
        # 3. Create Recurring Events (Mon-Sat 19:00)
        # We create 6 *Weekly* events, one for each day
        # Start date: Jan 26, 2026 (Monday)
        base_start_date = datetime(2026, 1, 26, 19, 0, 0)
        end_recurrence = base_start_date + timedelta(weeks=12) # 3 months course
        
        # Admin ID for creator (assuming ID 1 exists)
        creator_id = 1 
        
        days_offset = [0, 1, 2, 3, 4, 5] # Mon, Tue, Wed, Thu, Fri, Sat
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        
        print("Creating generic 'Online Class' recurring events...")
        
        for i, offset in enumerate(days_offset):
            start_dt = base_start_date + timedelta(days=offset)
            end_dt = start_dt + timedelta(minutes=90) # 1.5 hours
            
            # Create Recurring Event
            event = Event(
                title="Online Class", # User wanted generic title
                description="Zoom Lesson",
                event_type="class",
                start_datetime=start_dt,
                end_datetime=end_dt,
                location="Zoom/Online",
                is_online=True,
                is_active=True,
                is_recurring=True,
                recurrence_pattern="weekly",
                recurrence_end_date=end_recurrence.date(),
                created_by=creator_id,
                # Link to group
                event_groups=[EventGroup(group_id=group.id)]
            )
            db.add(event)
            print(f"  + Created weekly series starting {day_names[i]} {start_dt}")
            
        db.commit()
        print("Success! Schedule switched to Event-Based mode.")
            
    finally:
        db.close()

if __name__ == "__main__":
    switch_to_recurring_events()
