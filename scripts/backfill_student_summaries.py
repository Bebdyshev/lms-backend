#!/usr/bin/env python3
"""
Backfill script for StudentCourseSummary table.

This script populates the student_course_summaries table from existing
step_progress and assignment_submissions data. Run after applying the migration.

Usage:
    cd backend
    python scripts/backfill_student_summaries.py
"""
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func
from sqlalchemy.orm import Session
from src.config import SessionLocal
from src.schemas.models import (
    UserInDB, Course, Module, Lesson, Step, StepProgress,
    Assignment, AssignmentSubmission, Enrollment, GroupStudent,
    CourseGroupAccess, StudentCourseSummary, CourseAnalyticsCache
)


def get_user_courses(user_id: int, db: Session):
    """Get all courses accessible by a user."""
    # Via enrollment
    enrollment_ids = db.query(Enrollment.course_id).filter(
        Enrollment.user_id == user_id,
        Enrollment.is_active == True
    ).subquery()
    
    # Via group access
    group_ids = db.query(GroupStudent.group_id).filter(
        GroupStudent.student_id == user_id
    ).subquery()
    
    group_course_ids = db.query(CourseGroupAccess.course_id).filter(
        CourseGroupAccess.group_id.in_(group_ids),
        CourseGroupAccess.is_active == True
    ).subquery()
    
    from sqlalchemy import or_
    return db.query(Course).filter(
        or_(
            Course.id.in_(enrollment_ids),
            Course.id.in_(group_course_ids)
        ),
        Course.is_active == True
    ).all()


def backfill_student_summaries(db: Session, batch_size: int = 100):
    """Populate StudentCourseSummary from existing data."""
    print("Starting StudentCourseSummary backfill...")
    
    # Get all students
    students = db.query(UserInDB).filter(UserInDB.role == "student").all()
    print(f"Found {len(students)} students")
    
    created = 0
    updated = 0
    
    for i, student in enumerate(students):
        if i % 50 == 0:
            print(f"Processing student {i+1}/{len(students)}...")
        
        # Get courses for this student
        courses = get_user_courses(student.id, db)
        
        for course in courses:
            # Check if summary already exists
            existing = db.query(StudentCourseSummary).filter(
                StudentCourseSummary.user_id == student.id,
                StudentCourseSummary.course_id == course.id
            ).first()
            
            # Calculate metrics
            total_steps = db.query(func.count(Step.id)).join(Lesson).join(Module).filter(
                Module.course_id == course.id
            ).scalar() or 0
            
            completed_steps = db.query(func.count(StepProgress.id)).join(
                Step, StepProgress.step_id == Step.id
            ).join(Lesson, Step.lesson_id == Lesson.id).join(
                Module, Lesson.module_id == Module.id
            ).filter(
                StepProgress.user_id == student.id,
                Module.course_id == course.id,
                StepProgress.status == "completed"
            ).scalar() or 0
            
            completion_pct = (completed_steps / total_steps * 100) if total_steps > 0 else 0
            
            total_time = db.query(func.sum(StepProgress.time_spent_minutes)).join(
                Step, StepProgress.step_id == Step.id
            ).join(Lesson, Step.lesson_id == Lesson.id).join(
                Module, Lesson.module_id == Module.id
            ).filter(
                StepProgress.user_id == student.id,
                Module.course_id == course.id
            ).scalar() or 0
            
            # Assignment metrics
            total_assignments = db.query(func.count(Assignment.id)).join(
                Lesson
            ).join(Module).filter(
                Module.course_id == course.id,
                Assignment.is_active == True
            ).scalar() or 0
            
            assignment_stats = db.query(
                func.count(AssignmentSubmission.id),
                func.sum(AssignmentSubmission.score),
                func.sum(AssignmentSubmission.max_score)
            ).join(Assignment).join(Lesson).join(Module).filter(
                AssignmentSubmission.user_id == student.id,
                Module.course_id == course.id,
                AssignmentSubmission.is_graded == True
            ).first()
            
            completed_assignments = assignment_stats[0] or 0
            total_score = assignment_stats[1] or 0
            max_possible = assignment_stats[2] or 0
            avg_assignment_pct = (total_score / max_possible * 100) if max_possible > 0 else 0
            
            # Last activity
            last_progress = db.query(StepProgress).join(
                Step, StepProgress.step_id == Step.id
            ).join(Lesson, Step.lesson_id == Lesson.id).join(
                Module, Lesson.module_id == Module.id
            ).filter(
                StepProgress.user_id == student.id,
                Module.course_id == course.id
            ).order_by(StepProgress.visited_at.desc()).first()
            
            if existing:
                # Update existing
                existing.total_steps = total_steps
                existing.completed_steps = completed_steps
                existing.completion_percentage = completion_pct
                existing.total_time_spent_minutes = total_time
                existing.total_assignments = total_assignments
                existing.completed_assignments = completed_assignments
                existing.total_assignment_score = total_score
                existing.max_possible_score = max_possible
                existing.average_assignment_percentage = avg_assignment_pct
                if last_progress:
                    existing.last_activity_at = last_progress.visited_at
                    existing.last_lesson_id = last_progress.lesson_id
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                # Create new
                summary = StudentCourseSummary(
                    user_id=student.id,
                    course_id=course.id,
                    total_steps=total_steps,
                    completed_steps=completed_steps,
                    completion_percentage=completion_pct,
                    total_time_spent_minutes=total_time,
                    total_assignments=total_assignments,
                    completed_assignments=completed_assignments,
                    total_assignment_score=total_score,
                    max_possible_score=max_possible,
                    average_assignment_percentage=avg_assignment_pct,
                    last_activity_at=last_progress.visited_at if last_progress else None,
                    last_lesson_id=last_progress.lesson_id if last_progress else None
                )
                db.add(summary)
                created += 1
        
        # Commit in batches
        if (i + 1) % batch_size == 0:
            db.commit()
            print(f"  Committed batch at {i+1}")
    
    db.commit()
    print(f"Backfill complete: {created} created, {updated} updated")


def backfill_course_analytics(db: Session):
    """Populate CourseAnalyticsCache from existing data."""
    print("Starting CourseAnalyticsCache backfill...")
    
    courses = db.query(Course).filter(Course.is_active == True).all()
    print(f"Found {len(courses)} active courses")
    
    for course in courses:
        # Check if exists
        existing = db.query(CourseAnalyticsCache).filter(
            CourseAnalyticsCache.course_id == course.id
        ).first()
        
        # Calculate metrics
        total_enrolled = db.query(func.count(Enrollment.id)).filter(
            Enrollment.course_id == course.id,
            Enrollment.is_active == True
        ).scalar() or 0
        
        total_modules = db.query(func.count(Module.id)).filter(
            Module.course_id == course.id
        ).scalar() or 0
        
        total_lessons = db.query(func.count(Lesson.id)).join(Module).filter(
            Module.course_id == course.id
        ).scalar() or 0
        
        total_steps = db.query(func.count(Step.id)).join(Lesson).join(Module).filter(
            Module.course_id == course.id
        ).scalar() or 0
        
        total_assignments = db.query(func.count(Assignment.id)).join(
            Lesson
        ).join(Module).filter(
            Module.course_id == course.id,
            Assignment.is_active == True
        ).scalar() or 0
        
        # Average completion from summaries
        avg_completion = db.query(func.avg(StudentCourseSummary.completion_percentage)).filter(
            StudentCourseSummary.course_id == course.id
        ).scalar() or 0
        
        avg_assignment = db.query(func.avg(StudentCourseSummary.average_assignment_percentage)).filter(
            StudentCourseSummary.course_id == course.id
        ).scalar() or 0
        
        if existing:
            existing.total_enrolled = total_enrolled
            existing.total_modules = total_modules
            existing.total_lessons = total_lessons
            existing.total_steps = total_steps
            existing.total_assignments = total_assignments
            existing.average_completion_percentage = avg_completion
            existing.average_assignment_score = avg_assignment
            existing.last_calculated_at = datetime.utcnow()
        else:
            cache = CourseAnalyticsCache(
                course_id=course.id,
                total_enrolled=total_enrolled,
                total_modules=total_modules,
                total_lessons=total_lessons,
                total_steps=total_steps,
                total_assignments=total_assignments,
                average_completion_percentage=avg_completion,
                average_assignment_score=avg_assignment
            )
            db.add(cache)
    
    db.commit()
    print("CourseAnalyticsCache backfill complete")


def main():
    print("=" * 60)
    print("Student Course Summary Backfill Script")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        backfill_student_summaries(db)
        backfill_course_analytics(db)
    finally:
        db.close()
    
    print("\nBackfill completed successfully!")


if __name__ == "__main__":
    main()
