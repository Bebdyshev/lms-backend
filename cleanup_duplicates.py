
import sys
import os
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

# Add current directory to path to allow imports
sys.path.append(os.getcwd())

from src.schemas.models import Group, LessonSchedule, GroupAssignment
# Use hardcoded URL or try to load from .env manually if config import fails
# But earlier failure was due to bad import from src.config. Let's try fixing import path.
# Assuming run from backend root
from dotenv import load_dotenv
load_dotenv()

POSTGRES_URL = os.getenv("POSTGRES_URL")

def cleanup_duplicates():
    if not POSTGRES_URL:
        print("Error: POSTGRES_URL not found in environment.")
        return

    engine = create_engine(POSTGRES_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        print("Scanning for duplicate schedules...")
        
        # logic: Find (group_id, lesson_id) pairs with count > 1 where is_active=True
        duplicates = db.query(
            LessonSchedule.group_id,
            LessonSchedule.lesson_id,
            func.count(LessonSchedule.id)
        ).filter(
            LessonSchedule.is_active == True
        ).group_by(
            LessonSchedule.group_id,
            LessonSchedule.lesson_id
        ).having(func.count(LessonSchedule.id) > 1).all()
        
        print(f"Found {len(duplicates)} duplicate sets.")
        
        fixed_count = 0
        
        for group_id, lesson_id, count in duplicates:
            # Fetch the actual records
            records = db.query(LessonSchedule).filter(
                LessonSchedule.group_id == group_id,
                LessonSchedule.lesson_id == lesson_id,
                LessonSchedule.is_active == True
            ).order_by(LessonSchedule.id.desc()).all() # Newest first
            
            # Keep records[0], deactivate the rest
            to_remove = records[1:]
            
            for sched in to_remove:
                print(f"Deactivating duplicate: ID {sched.id} (Group {group_id}, Lesson {lesson_id})")
                sched.is_active = False
                
                # Cleanup associated GroupAssignments
                gas = db.query(GroupAssignment).filter(
                    GroupAssignment.lesson_schedule_id == sched.id,
                    GroupAssignment.is_active == True
                ).all()
                for ga in gas:
                    ga.is_active = False
                    
                fixed_count += 1
                
        db.commit()
        print(f"Cleanup complete. Fixed {fixed_count} duplicate records.")
            
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_duplicates()
