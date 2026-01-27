from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, date, timedelta

from src.config import get_db
from src.schemas.models import (
    UserInDB, Group, GroupStudent, Assignment, AssignmentSubmission, Lesson, Module, Course,
    LeaderboardEntry, LeaderboardEntrySchema, LeaderboardEntryCreateSchema,
    GroupSchema, LessonSchedule, Attendance, AttendanceSchema, GroupAssignment
)
from pydantic import BaseModel
from src.routes.auth import get_current_user_dependency

router = APIRouter()

@router.get("/curator/groups", response_model=List[GroupSchema])
async def get_curator_groups(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get groups managed by average curator"""
    if current_user.role == "admin" or current_user.role == "head_curator":
        groups = db.query(Group).all()
    elif current_user.role == "curator":
        groups = db.query(Group).filter(Group.curator_id == current_user.id).all()
    else:
        raise HTTPException(status_code=403, detail="Only curators and admins can access this endpoint")
    # We need to return GroupSchema. Since GroupSchema has many fields, we might need to populate them or use a simplified schema.
    # The frontend only uses id and name for the dropdown.
    # But for compatibility, let's use GroupSchema and fill basics.
    
    result = []
    for group in groups:
        # Simplified population since we just need the list
        result.append(GroupSchema(
            id=group.id,
            name=group.name,
            description=group.description,
            teacher_id=group.teacher_id,
            teacher_name="", # Not critical for dropdown
            curator_id=group.curator_id,
            curator_name=current_user.name,
            student_count=0, # Not critical
            students=[],
            created_at=group.created_at,
            is_active=group.is_active
        ))
    return result

@router.get("/curator/leaderboard/{group_id}", response_model=List[dict])
async def get_group_leaderboard(
    group_id: int,
    week_number: int = Query(..., ge=1, le=52),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get leaderboard data for a specific group and week.
    Supports dynamic LessonSchedule or falls back to legacy 5-lesson logic.
    """
    if current_user.role == "curator":
        group = db.query(Group).filter(Group.id == group_id, Group.curator_id == current_user.id).first()
        if not group:
            raise HTTPException(status_code=403, detail="Access denied to this group")
    elif current_user.role in ["admin", "head_curator"]:
        pass
    else:
        raise HTTPException(status_code=403, detail="Only curators and admins can access leaderboard")

    # 1. Get all students in the group
    group_students = db.query(GroupStudent).filter(GroupStudent.group_id == group_id).all()
    student_ids = [gs.student_id for gs in group_students]
    
    if not student_ids:
        return []
        
    students = db.query(UserInDB).filter(UserInDB.id.in_(student_ids)).all()
    students_map = {s.id: s for s in students}

    # 2. Key logic: Map Week Number to Lesson IDs using LessonSchedule
    # Try to find schedules for this week
    schedules = db.query(LessonSchedule).filter(
        LessonSchedule.group_id == group_id,
        LessonSchedule.week_number == week_number,
        LessonSchedule.is_active == True
    ).order_by(LessonSchedule.scheduled_at).all()
    
    homework_data = {} # {student_id: {schedule_id: score}}
    attendance_data = {} # {student_id: {schedule_id: score}}
    
    scheduled_lesson_ids = []
    
    if schedules:
        # Use Dynamic Schedule Logic
        scheduled_lesson_ids = [s.lesson_id for s in schedules]
        schedule_map = {s.id: s for s in schedules}
        schedule_ids = [s.id for s in schedules]
        
        # Get Assignments for these lessons
        assignments = db.query(Assignment).filter(
            Assignment.lesson_id.in_(scheduled_lesson_ids),
            Assignment.is_active == True
        ).all()
        
        assignment_lesson_map = {a.id: a.lesson_id for a in assignments}
        assignment_ids = [a.id for a in assignments]
        
        # Map lesson_id to schedule_index (1-based)
        lesson_to_schedule_indices = {} 
        for idx, s in enumerate(schedules):
            if s.lesson_id not in lesson_to_schedule_indices:
                lesson_to_schedule_indices[s.lesson_id] = []
            lesson_to_schedule_indices[s.lesson_id].append(idx + 1)

        # Get Submissions
        submissions = db.query(AssignmentSubmission).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids),
            AssignmentSubmission.user_id.in_(student_ids),
            AssignmentSubmission.is_graded == True
        ).all()
        
        for sub in submissions:
            lid = assignment_lesson_map.get(sub.assignment_id)
            indices = lesson_to_schedule_indices.get(lid, [])
            for idx in indices:
                if sub.user_id not in homework_data:
                    homework_data[sub.user_id] = {}
                homework_data[sub.user_id][idx] = sub.score
                
        # Get Attendance
        attendances = db.query(Attendance).filter(
            Attendance.lesson_schedule_id.in_(schedule_ids),
            Attendance.user_id.in_(student_ids)
        ).all()
        
        for att in attendances:
            if att.user_id not in attendance_data:
                attendance_data[att.user_id] = {}
            # Find schedule index
            sched = schedule_map.get(att.lesson_schedule_id)
            if sched:
                try:
                    idx = schedules.index(sched) + 1
                    attendance_data[att.user_id][idx] = att.score
                except ValueError:
                    pass

    else:
        # FALLBACK: Legacy Logic (No schedules found)
        start_lesson_index = (week_number - 1) * 5
        from src.schemas.models import CourseGroupAccess
        course_access = db.query(CourseGroupAccess).filter(
            CourseGroupAccess.group_id == group_id,
            CourseGroupAccess.is_active == True
        ).first()

        if course_access:
            lessons_query = db.query(Lesson).join(Module).filter(
                Module.course_id == course_access.course_id
            ).order_by(Module.order_index, Lesson.order_index).offset(start_lesson_index).limit(5).all()
            
            target_lesson_ids = [l.id for l in lessons_query]
            
            assignments = db.query(Assignment).filter(
                Assignment.lesson_id.in_(target_lesson_ids),
                Assignment.is_active == True
            ).all()
            
            assignment_lesson_map = {a.id: a.lesson_id for a in assignments}
            assignment_ids = [a.id for a in assignments]
            
            def get_week_lesson_index(lesson_id):
                try:
                    return target_lesson_ids.index(lesson_id) + 1
                except ValueError:
                    return 0

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
                    homework_data[sub.user_id][week_idx] = sub.score

    # 3. Get Manual Leaderboard Entries (Still needed for other columns)
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
        att_scores = attendance_data.get(student_id, {})
        
        # Manual scores defaults
        manual = {
            "curator_hour": entry.curator_hour if entry else 0,
            "mock_exam": entry.mock_exam if entry else 0,
            "study_buddy": entry.study_buddy if entry else 0,
            "self_reflection_journal": entry.self_reflection_journal if entry else 0,
            "weekly_evaluation": entry.weekly_evaluation if entry else 0,
            "extra_points": entry.extra_points if entry else 0,
        }
        
        # Merge Attendance and Legacy Manual Lesson Scores
        lesson_scores = {}
        for i in range(1, 6):
            if schedules:
                 # Use attendance data
                 lesson_scores[f"lesson_{i}"] = att_scores.get(i, 0)
            else:
                 # Use legacy manual data
                 key = f"lesson_{i}"
                 lesson_scores[key] = getattr(entry, key) if entry else 0
        
        row = {
            "student_id": student.id,
            "student_name": student.name,
            "avatar_url": student.avatar_url,
            "hw_lesson_1": hw_scores.get(1, None),
            "hw_lesson_2": hw_scores.get(2, None),
            "hw_lesson_3": hw_scores.get(3, None),
            "hw_lesson_4": hw_scores.get(4, None),
            "hw_lesson_5": hw_scores.get(5, None),
            **lesson_scores,
            **manual
        }
        result.append(row)

    # Sort by name
    result.sort(key=lambda x: x["student_name"])
    
    return result
    """
    Get leaderboard data for a specific group and week.
    Calculates homework scores automatically based on week number (5 lessons per week).
    """
    if current_user.role == "curator":
        group = db.query(Group).filter(Group.id == group_id, Group.curator_id == current_user.id).first()
        if not group:
            raise HTTPException(status_code=403, detail="Access denied to this group")
    elif current_user.role in ["admin", "head_curator"]:
        pass
    else:
        raise HTTPException(status_code=403, detail="Only curators and admins can access leaderboard")

    # 1. Get all students in the group
    group_students = db.query(GroupStudent).filter(GroupStudent.group_id == group_id).all()
    student_ids = [gs.student_id for gs in group_students]
    
    if not student_ids:
        return []
        
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
            "lesson_1": entry.lesson_1 if entry else 0,
            "lesson_2": entry.lesson_2 if entry else 0,
            "lesson_3": entry.lesson_3 if entry else 0,
            "lesson_4": entry.lesson_4 if entry else 0,
            "lesson_5": entry.lesson_5 if entry else 0,
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
    if current_user.role == "curator":
         group = db.query(Group).filter(
             Group.id == data.group_id, 
             Group.curator_id == current_user.id
         ).first()
         if not group:
             raise HTTPException(status_code=403, detail="Access denied to this group")
    elif current_user.role in ["admin", "head_curator"]:
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

class AttendanceInputSchema(BaseModel):
    group_id: int
    week_number: int
    lesson_index: int # 1-5
    student_id: int
    score: int
    status: str = "present"

@router.post("/curator/attendance")
async def update_attendance(
    data: AttendanceInputSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Update attendance score for a specific scheduled lesson.
    If no schedule exists, it fails (or should we fallback to manual columns in LeaderboardEntry?).
    Decision: Support both?
    If schedule exists -> update Attendance model.
    If schedule does not exist -> update LeaderboardEntry model (legacy).
    """
    
    # Auth
    if current_user.role not in ["curator", "admin", "head_curator"]:
        raise HTTPException(status_code=403, detail="Access denied")
        
    group = db.query(Group).filter(Group.id == data.group_id).first()
    if not group:
         raise HTTPException(status_code=404, detail="Group not found")
         
    if current_user.role == "curator" and group.curator_id != current_user.id:
         raise HTTPException(status_code=403, detail="Access denied to this group")

    # Check for schedule
    schedules = db.query(LessonSchedule).filter(
        LessonSchedule.group_id == data.group_id,
        LessonSchedule.week_number == data.week_number,
        LessonSchedule.is_active == True
    ).order_by(LessonSchedule.scheduled_at).all()
    
    if schedules and 0 < data.lesson_index <= len(schedules):
        # Update Attendance Model
        target_schedule = schedules[data.lesson_index - 1]
        
        attendance = db.query(Attendance).filter(
            Attendance.lesson_schedule_id == target_schedule.id,
            Attendance.user_id == data.student_id
        ).first()
        
        if attendance:
            attendance.score = data.score
            attendance.status = data.status
        else:
            attendance = Attendance(
                lesson_schedule_id=target_schedule.id,
                user_id=data.student_id,
                score=data.score,
                status=data.status
            )
            db.add(attendance)
        db.commit()
        return {"status": "success", "mode": "schedule"}
        
    else:
        # Fallback to LeaderboardEntry (Legacy)
        # Check if 1 <= lesson_index <= 5
        if not (1 <= data.lesson_index <= 5):
             raise HTTPException(status_code=400, detail="Invalid lesson index")
             
        entry = db.query(LeaderboardEntry).filter(
            LeaderboardEntry.user_id == data.student_id,
            LeaderboardEntry.group_id == data.group_id,
            LeaderboardEntry.week_number == data.week_number
        ).first()
        
        if not entry:
            entry = LeaderboardEntry(
                user_id=data.student_id,
                group_id=data.group_id,
                week_number=data.week_number
            )
            db.add(entry)
            
        # Update specific column
        # lesson_1, lesson_2 ...
        col_name = f"lesson_{data.lesson_index}"
        setattr(entry, col_name, float(data.score)) # Ensure float for legacy compatibility
        
        db.commit()
        return {"status": "success", "mode": "legacy"}

class ScheduleItem(BaseModel):
    day_of_week: int # 0=Mon, ... 6=Sun
    time_of_day: str # "18:00"

class ScheduleGenerationSchema(BaseModel):
    group_id: int
    start_date: date
    schedule_items: List[ScheduleItem]
    weeks_count: int = 12

@router.post("/curator/schedule/generate")
async def generate_schedule(
    data: ScheduleGenerationSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Generate lesson schedules for a group.
    Iteratively finds lessons in the course and schedules them.
    Also creates GroupAssignment records for automated homework tracking.
    """
    if current_user.role not in ["curator", "admin"]:
       raise HTTPException(status_code=403, detail="Access denied")

    # Fetch group and course
    from src.schemas.models import CourseGroupAccess
    
    course_access = db.query(CourseGroupAccess).filter(
        CourseGroupAccess.group_id == data.group_id,
        CourseGroupAccess.is_active == True
    ).first()
    
    if not course_access:
        raise HTTPException(status_code=400, detail="Group has no active course")
        
    # Fetch all lessons
    lessons = db.query(Lesson).join(Module).filter(
        Module.course_id == course_access.course_id
    ).order_by(Module.order_index, Lesson.order_index).all()
    
    if not lessons:
        raise HTTPException(status_code=400, detail="Course has no lessons")

    # Parse times
    # schedule_items_map = { day_int: time_obj }
    schedule_config = {}
    for item in data.schedule_items:
        try:
            t = datetime.strptime(item.time_of_day, "%H:%M").time()
            schedule_config[item.day_of_week] = t
        except ValueError:
             raise HTTPException(status_code=400, detail=f"Invalid time format for day {item.day_of_week}, use HH:MM")
    
    if not schedule_config:
        raise HTTPException(status_code=400, detail="No schedule days provided")

    # Generate dates
    current_date = data.start_date
    schedules = []
    generated_count = 0
    total_weeks = data.weeks_count
    
    # Move to first scheduled day
    while current_date.weekday() not in schedule_config:
        current_date += timedelta(days=1)
        
    for lesson in lessons:
        days_diff = (current_date - data.start_date).days
        week_num = (days_diff // 7) + 1
        
        if week_num > total_weeks:
            break
             
        # Create schedule
        schedule_time = schedule_config[current_date.weekday()]
        dt = datetime.combine(current_date, schedule_time)
        
        sched = LessonSchedule(
            group_id=data.group_id,
            lesson_id=lesson.id,
            scheduled_at=dt,
            week_number=week_num,
            is_active=True
        )
        db.add(sched)
        db.flush() # flush to get sched.id
        schedules.append(sched)
        generated_count += 1
        
        # Automated Homework Assignment
        lesson_assignments = db.query(Assignment).filter(
            Assignment.lesson_id == lesson.id,
            Assignment.is_active == True
        ).all()
        
        for assign in lesson_assignments:
            due = dt + timedelta(days=7) # Default 1 week due date
            
            ga = GroupAssignment(
                group_id=data.group_id,
                assignment_id=assign.id,
                lesson_schedule_id=sched.id,
                assigned_at=dt,
                due_date=due,
                is_active=True
            )
            db.add(ga)
        
        # Move to next slot
        current_date += timedelta(days=1)
        while current_date.weekday() not in schedule_config:
            current_date += timedelta(days=1)
            
    db.commit()
    return {"status": "success", "count": len(schedules)}

# ==================== STUDENT LEADERBOARD ====================

from src.schemas.models import StepProgress
from datetime import timedelta

@router.get("/student/my-ranking")
async def get_student_ranking(
    period: str = Query("all_time", regex="^(all_time|this_week|this_month)$"),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get leaderboard for current student's group.
    Shows ranking by completed steps and time spent.
    Perfect for competitive students who want to flex 💪
    """
    
    if current_user.role not in ['student', 'admin']:
        raise HTTPException(status_code=403, detail="This endpoint is for students only")
    
    # Find user's group
    group_membership = db.query(GroupStudent).filter(
        GroupStudent.student_id == current_user.id
    ).first()
    
    group_id = None
    group_name = None
    student_ids = []
    
    if group_membership:
        group = db.query(Group).filter(Group.id == group_membership.group_id).first()
        if group:
            group_id = group.id
            group_name = group.name
            
            # Get all students in this group
            group_students = db.query(GroupStudent).filter(
                GroupStudent.group_id == group.id
            ).all()
            student_ids = [gs.student_id for gs in group_students]
    
    if not student_ids:
        # User is not in any group, show global leaderboard for students
        students = db.query(UserInDB).filter(
            UserInDB.role == 'student',
            UserInDB.is_active == True
        ).limit(100).all()
        student_ids = [s.id for s in students]
        group_name = "Global Rankings"
    
    # Calculate time filter
    time_filter = None
    now = datetime.utcnow()
    
    if period == "this_week":
        # Start of current week (Monday)
        start_of_week = now - timedelta(days=now.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        time_filter = start_of_week
    elif period == "this_month":
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        time_filter = start_of_month
    
    # Build query for progress stats
    progress_query = db.query(
        StepProgress.user_id,
        func.count(StepProgress.id).label('steps_completed'),
        func.coalesce(func.sum(StepProgress.time_spent_minutes), 0).label('time_spent')
    ).filter(
        StepProgress.user_id.in_(student_ids),
        StepProgress.status == 'completed'
    )
    
    if time_filter:
        progress_query = progress_query.filter(StepProgress.completed_at >= time_filter)
    
    progress_stats = progress_query.group_by(StepProgress.user_id).all()
    
    # Create stats dictionary
    stats_dict = {
        stat.user_id: {
            'steps_completed': stat.steps_completed,
            'time_spent_minutes': int(stat.time_spent)
        }
        for stat in progress_stats
    }
    
    # Get all student info
    students = db.query(UserInDB).filter(UserInDB.id.in_(student_ids)).all()
    
    # Build leaderboard entries
    entries = []
    for student in students:
        stats = stats_dict.get(student.id, {'steps_completed': 0, 'time_spent_minutes': 0})
        entries.append({
            'user_id': student.id,
            'user_name': student.name or student.email.split('@')[0],
            'avatar_url': student.avatar_url,
            'steps_completed': stats['steps_completed'],
            'time_spent_minutes': stats['time_spent_minutes'],
            'is_current_user': student.id == current_user.id
        })
    
    # Sort by steps completed (primary), then by time spent (secondary)
    entries.sort(key=lambda x: (-x['steps_completed'], -x['time_spent_minutes']))
    
    # Add ranks and find current user
    leaderboard = []
    current_user_rank = 0
    current_user_entry = None
    
    for i, entry in enumerate(entries):
        rank = i + 1
        leaderboard_entry = {
            'rank': rank,
            'user_id': entry['user_id'],
            'user_name': entry['user_name'],
            'avatar_url': entry['avatar_url'],
            'steps_completed': entry['steps_completed'],
            'time_spent_minutes': entry['time_spent_minutes'],
            'is_current_user': entry['is_current_user']
        }
        leaderboard.append(leaderboard_entry)
        
        if entry['is_current_user']:
            current_user_rank = rank
            current_user_entry = leaderboard_entry
    
    # Calculate steps to next rank
    steps_to_next_rank = 0
    if current_user_rank > 1 and current_user_entry:
        # Find the person ahead
        person_ahead = leaderboard[current_user_rank - 2]  # -2 because rank is 1-indexed and we need previous
        steps_to_next_rank = person_ahead['steps_completed'] - current_user_entry['steps_completed'] + 1
        if steps_to_next_rank < 0:
            steps_to_next_rank = 0
    
    # Fun titles based on rank
    def get_rank_title(rank: int, total: int) -> str:
        if rank == 1:
            return "👑 The GOAT"
        elif rank == 2:
            return "🥈 Almost There"
        elif rank == 3:
            return "🥉 Bronze Legend"
        elif rank <= 5:
            return "🔥 On Fire"
        elif rank <= total * 0.25:
            return "💪 Top 25%"
        elif rank <= total * 0.5:
            return "📈 Rising Star"
        else:
            return "🚀 Just Getting Started"
    
    return {
        "group_id": group_id,
        "group_name": group_name,
        "leaderboard": leaderboard[:20],  # Top 20
        "current_user_rank": current_user_rank,
        "current_user_entry": current_user_entry,
        "current_user_title": get_rank_title(current_user_rank, len(entries)) if current_user_rank > 0 else "🎯 No Progress Yet",
        "total_participants": len(entries),
        "period": period,
        "steps_to_next_rank": steps_to_next_rank
    }
