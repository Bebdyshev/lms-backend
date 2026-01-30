from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.models import (
    User, Course, Group, CourseGroupAccess, Assignment, AssignmentSubmission, CourseHeadTeacher
)
from datetime import datetime, timedelta

# Setup DB connection (assuming standard local env from running app)
# You might need to adjust the URL if it's different in .env
SQLALCHEMY_DATABASE_URL = "postgresql://myuser:mypassword@localhost:5432/lms_db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

course_id = 1
days = 30
now = datetime.utcnow()
start_date = (now - timedelta(days=days)).date()

print(f"Checking data for Course ID: {course_id} from {start_date} to {now.date()}")

# 1. Check Course Existence
course = db.query(Course).filter(Course.id == course_id).first()
if not course:
    print("Course not found!")
else:
    print(f"Course found: {course.title}")

# 2. Check Groups linked to Course
group_ids = [
    ga.group_id for ga in db.query(CourseGroupAccess)
    .filter(CourseGroupAccess.course_id == course_id, CourseGroupAccess.is_active == True)
    .all()
]
print(f"Linked Group IDs: {group_ids}")

# 3. Check Assignments
if group_ids:
    assignment_ids = [
        a.id for a in db.query(Assignment)
        .filter(Assignment.group_id.in_(group_ids), Assignment.is_active == True)
        .all()
    ]
    print(f"Found {len(assignment_ids)} assignments.")
    
    # 4. Check Graded Submissions
    if assignment_ids:
        # Check Total Graded
        total_graded = db.query(AssignmentSubmission).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids),
            AssignmentSubmission.is_graded == True
        ).count()
        print(f"Total graded submissions (ALL TIME): {total_graded}")

        # Check Graded with valid graded_at
        graded_with_date = db.query(AssignmentSubmission).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids),
            AssignmentSubmission.is_graded == True,
            AssignmentSubmission.graded_at.isnot(None)
        ).count()
        print(f"Graded submissions with graded_at set: {graded_with_date}")
        
        # Check Graded in Range
        in_range = db.query(AssignmentSubmission).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids),
            AssignmentSubmission.is_graded == True,
            AssignmentSubmission.graded_at >= start_date
        ).all()
        print(f"Graded submissions since {start_date}: {len(in_range)}")
        
        # Print sample dates if any
        if in_range:
            print("Sample graded_at dates:")
            for sub in in_range[:5]:
                print(f" - ID {sub.id}: {sub.graded_at}")
    else:
        print("No assignments found.")
else:
    print("No groups linked.")

db.close()
