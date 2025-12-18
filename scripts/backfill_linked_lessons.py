import os
import sys
import json

# Add parent directory to path to import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import SessionLocal
from src.schemas.models import Assignment, AssignmentLinkedLesson
from src.routes.assignments import sync_assignment_linked_lessons

def backfill():
    db = SessionLocal()
    try:
        # Get all active assignments
        assignments = db.query(Assignment).filter(Assignment.is_active == True).all()
        print(f"Found {len(assignments)} active assignments to process.")
        
        for assignment in assignments:
            print(f"Processing assignment {assignment.id}: {assignment.title}")
            sync_assignment_linked_lessons(assignment, db)
            
        print("Backfill completed successfully.")
    except Exception as e:
        print(f"Error during backfill: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    backfill()
