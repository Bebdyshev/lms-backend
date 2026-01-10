"""
Script to mark existing students as having completed Assignment Zero.
This should be run once after implementing the Assignment Zero feature.
Students created before this feature don't need to complete it.
"""

import sys
sys.path.insert(0, '/Users/bebdyshev/Documents/Github/lms/backend')

from datetime import datetime
from sqlalchemy.orm import Session
from src.config import engine, SessionLocal
from src.schemas.models import User

def fix_existing_students():
    db: Session = SessionLocal()
    try:
        # Get all students who have assignment_zero_completed = False
        # but don't have an AssignmentZeroSubmission
        students = db.query(User).filter(
            User.role == 'student',
            User.assignment_zero_completed == False
        ).all()
        
        print(f"Found {len(students)} students with assignment_zero_completed = False")
        
        # Mark them all as completed (they are existing students before this feature)
        for student in students:
            student.assignment_zero_completed = True
            print(f"  - Marking {student.email} as completed")
        
        db.commit()
        print(f"\nSuccessfully updated {len(students)} students")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_existing_students()
