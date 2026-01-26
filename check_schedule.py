
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add current directory to path to allow imports
sys.path.append(os.getcwd())

from src.config import POSTGRES_URL 
from src.schemas.models import Group, LessonSchedule, Lesson

def check_schedule():
    engine = create_engine(POSTGRES_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # 1. Find the group
        group_name = "Intensive 1"
        group = db.query(Group).filter(Group.name.ilike(f"%{group_name}%")).first()
        
        if not group:
            print(f"Group '{group_name}' not found.")
            return

        print(f"Found Group: {group.name} (ID: {group.id})")
        
        # 2. Get Schedule
        schedules = db.query(LessonSchedule).filter(
            LessonSchedule.group_id == group.id,
            LessonSchedule.is_active == True
        ).order_by(LessonSchedule.scheduled_at).all()
        
        if not schedules:
            print("No active schedule found for this group.")
            return
            
        print(f"\n--- Schedule for {group.name} ---")
        print(f"{'Week':<5} | {'Date':<20} | {'Lesson Title'}")
        print("-" * 60)
        
        for sched in schedules:
            lesson_title = sched.lesson.title if sched.lesson else "No Lesson Linked"
            print(f"{sched.week_number:<5} | {str(sched.scheduled_at):<20} | {lesson_title}")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_schedule()
