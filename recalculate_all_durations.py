"""
Script to recalculate estimated_duration_minutes for all existing courses.
Run this once to update all courses with calculated durations.
"""
import sys
import os

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from src.config import SessionLocal
from src.schemas.models import Course
from src.utils.duration_calculator import update_course_duration


def recalculate_all_courses():
    """Recalculate duration for all courses in the database"""
    db: Session = SessionLocal()
    
    try:
        # Get all courses
        courses = db.query(Course).all()
        
        print(f"Found {len(courses)} courses to process...")
        
        updated_count = 0
        for course in courses:
            print(f"\nProcessing course: {course.id} - {course.title}")
            old_duration = course.estimated_duration_minutes
            
            # Calculate new duration
            new_duration = update_course_duration(course.id, db)
            
            print(f"  Old duration: {old_duration} minutes")
            print(f"  New duration: {new_duration} minutes")
            
            if old_duration != new_duration:
                updated_count += 1
                print(f"  ✓ Updated")
            else:
                print(f"  - No change")
        
        print(f"\n{'='*60}")
        print(f"Recalculation complete!")
        print(f"Total courses: {len(courses)}")
        print(f"Updated courses: {updated_count}")
        print(f"Unchanged courses: {len(courses) - updated_count}")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting course duration recalculation...")
    print("=" * 60)
    recalculate_all_courses()
