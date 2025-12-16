from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime

from src.config import get_db
from src.schemas.models import (
    UserInDB, Group, GroupStudent, Assignment, AssignmentSubmission, Lesson, Module, Course,
    LeaderboardEntry, LeaderboardEntrySchema, LeaderboardEntryCreateSchema
)
from src.routes.auth import get_current_user_dependency

router = APIRouter()

@router.get("/curator/leaderboard/{group_id}")
async def get_group_leaderboard(
    group_id: int,
    week_number: int = Query(..., ge=1, le=52),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get leaderboard data for a specific group and week.
    Calculates homework scores automatically based on week number (5 lessons per week).
    """
    # Authorization check
    if current_user.role == "curator":
        group = db.query(Group).filter(Group.id == group_id, Group.curator_id == current_user.id).first()
        if not group:
            raise HTTPException(status_code=403, detail="Access denied to this group")
    elif current_user.role == "admin":
        pass
    else:
        raise HTTPException(status_code=403, detail="Only curators and admins can access leaderboard")

    # 1. Get all students in the group
    group_students = db.query(GroupStudent).filter(GroupStudent.group_id == group_id).all()
    student_ids = [gs.student_id for gs in group_students]
    
    if not student_ids:
        return {"students": []}
        
    students = db.query(UserInDB).filter(UserInDB.id.in_(student_ids)).all()
    students_map = {s.id: s for s in students}

    # 2. Key logic: Map Week Number to Lesson IDs
    # Assumption: Week 1 = Assignments from Lessons 1-5, Week 2 = Lessons 6-10, etc.
    start_lesson_index = (week_number - 1) * 5
    # We need to find assignments that belong to the course of this group
    # Logic: Group -> CourseGroupAccess -> Course -> Modules -> Lessons
    from src.schemas.models import CourseGroupAccess
    
    course_access = db.query(CourseGroupAccess).filter(
        CourseGroupAccess.group_id == group_id,
        CourseGroupAccess.is_active == True
    ).first()
    
    homework_data = {} # {student_id: {lesson_index (1-5): score}}
    
    if course_access:
        # Get lessons for this course ordered by index
        lessons_query = db.query(Lesson).join(Module).filter(
            Module.course_id == course_access.course_id
        ).order_by(Module.order_index, Lesson.order_index).offset(start_lesson_index).limit(5).all()
        
        target_lesson_ids = [l.id for l in lessons_query]
        
        # Get assignments for these lessons
        assignments = db.query(Assignment).filter(
            Assignment.lesson_id.in_(target_lesson_ids),
            Assignment.is_active == True
        ).all()
        
        assignment_lesson_map = {a.id: a.lesson_id for a in assignments}
        assignment_ids = [a.id for a in assignments]
        
        # Helper to map actual lesson ID to 1-5 relative index for the week
        # target_lesson_ids is already ordered. index 0 -> "Lesson 1" of the week
        def get_week_lesson_index(lesson_id):
            try:
                return target_lesson_ids.index(lesson_id) + 1
            except ValueError:
                return 0

        # Get submissions
        submissions = db.query(AssignmentSubmission).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids),
            AssignmentSubmission.user_id.in_(student_ids),
            AssignmentSubmission.is_graded == True
        ).all()
        
        for sub in submissions:
            lid = assignment_lesson_map.get(sub.assignment_id)
            week_idx = get_week_lesson_index(lid)
            if week_idx > 0:
                if sub.user_id not in homework_data:
                    homework_data[sub.user_id] = {}
                # Take highest score if multiple? Or just list? Assuming one active submission for now
                # Or average if multiple assignments per lesson?
                # Let's simple: store score
                homework_data[sub.user_id][week_idx] = sub.score

    # 3. Get Manual Leaderboard Entries
    entries = db.query(LeaderboardEntry).filter(
        LeaderboardEntry.group_id == group_id,
        LeaderboardEntry.week_number == week_number
    ).all()
    entries_map = {e.user_id: e for e in entries}

    # 4. Construct Response
    result = []
    for student_id in student_ids:
        student = students_map.get(student_id)
        if not student: 
            continue
            
        entry = entries_map.get(student_id)
        hw_scores = homework_data.get(student_id, {})
        
        # Manual scores defaults
        manual = {
            "curator_hour": entry.curator_hour if entry else 0,
            "mock_exam": entry.mock_exam if entry else 0,
            "study_buddy": entry.study_buddy if entry else 0,
            "self_reflection_journal": entry.self_reflection_journal if entry else 0,
            "weekly_evaluation": entry.weekly_evaluation if entry else 0,
            "extra_points": entry.extra_points if entry else 0,
        }
        
        # Calculate derived totals (Total HW + Total Manual)
        # Note: Frontend handles display, but calculating here helps backend integrity
        
        row = {
            "student_id": student.id,
            "student_name": student.name,
            "avatar_url": student.avatar_url,
            "hw_lesson_1": hw_scores.get(1, None),
            "hw_lesson_2": hw_scores.get(2, None),
            "hw_lesson_3": hw_scores.get(3, None),
            "hw_lesson_4": hw_scores.get(4, None),
            "hw_lesson_5": hw_scores.get(5, None),
            **manual
        }
        result.append(row)

    # Sort by name
    result.sort(key=lambda x: x["student_name"])
    
    return result

@router.post("/curator/leaderboard")
async def update_leaderboard_entry(
    data: LeaderboardEntryCreateSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Update or create a manual leaderboard entry.
    """
    # Auth check
    if current_user.role == "curator":
         group = db.query(Group).filter(
             Group.id == data.group_id, 
             Group.curator_id == current_user.id
         ).first()
         if not group:
             raise HTTPException(status_code=403, detail="Access denied to this group")
    elif current_user.role == "admin":
        pass
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check existence
    entry = db.query(LeaderboardEntry).filter(
        LeaderboardEntry.user_id == data.user_id,
        LeaderboardEntry.group_id == data.group_id,
        LeaderboardEntry.week_number == data.week_number
    ).first()
    
    if entry:
        # Update existing fields if provided
        for field, value in data.dict(exclude_unset=True).items():
            if field not in ['user_id', 'group_id', 'week_number']:
                setattr(entry, field, value)
    else:
        # Create new
        entry = LeaderboardEntry(**data.dict())
        db.add(entry)
    
    db.commit()
    db.refresh(entry)
    return entry
