from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from typing import List, Optional
from datetime import datetime, date, timedelta

from src.config import get_db
from src.schemas.models import (
    UserInDB, Group, GroupStudent, Assignment, AssignmentSubmission, Lesson, Module, Course,
    LeaderboardEntry, LeaderboardEntrySchema, LeaderboardEntryCreateSchema,
    GroupSchema, LessonSchedule, Attendance, AttendanceSchema, GroupAssignment,
    LeaderboardConfig, LeaderboardConfigSchema, LeaderboardConfigUpdateSchema,
    CourseGroupAccess, Event, EventGroup, EventParticipant
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
    
    
    # 3. Calculate current_week for each group
    from src.schemas.models import Event, EventGroup, LessonSchedule
    
    result = []
    for group in groups:
        # Determine Week 1 Start (same logic as get_weekly_lessons_with_hw_status)
        first_event = db.query(Event).join(EventGroup).filter(
            EventGroup.group_id == group.id,
            Event.event_type == 'class',
            Event.is_active == True
        ).order_by(Event.start_datetime.asc()).first()
        
        start_of_week1 = None
        if first_event:
            start_of_week1 = first_event.start_datetime.date()
        else:
            first_sched = db.query(LessonSchedule).filter(
                LessonSchedule.group_id == group.id,
                LessonSchedule.is_active == True
            ).order_by(LessonSchedule.scheduled_at.asc()).first()
            if first_sched:
                start_of_week1 = first_sched.scheduled_at.date()
        
        current_week = 1
        max_week = 52
        if start_of_week1:
             # Align to Monday
            start_of_week1 = start_of_week1 - timedelta(days=start_of_week1.weekday())
            now_date = datetime.utcnow().date()
            
            # Calculate calendar week difference
            days_diff = (now_date - start_of_week1).days
            calendar_week = (days_diff // 7) + 1
            if calendar_week < 1: 
                calendar_week = 1
                
            # Calculate Max Content Week (Last scheduled event)
            last_event = db.query(Event).join(EventGroup).filter(
                EventGroup.group_id == group.id,
                Event.event_type == 'class',
                Event.is_active == True
            ).order_by(Event.start_datetime.desc()).first()
            
            last_date = None
            if last_event:
                last_date = last_event.start_datetime.date()
            else:
                last_sched = db.query(LessonSchedule).filter(
                    LessonSchedule.group_id == group.id,
                    LessonSchedule.is_active == True
                ).order_by(LessonSchedule.scheduled_at.desc()).first()
                if last_sched:
                    last_date = last_sched.scheduled_at.date()
            
            max_content_week = 1
            if last_date:
                 last_diff = (last_date - start_of_week1).days
                 max_content_week = (last_diff // 7) + 1
                 if max_content_week < 1: max_content_week = 1
            
            # 3.5 Also consider Course Length (Total lessons / 5)
            from src.schemas.models import CourseGroupAccess, Lesson, Module
            course_max_week = 1
            course_access = db.query(CourseGroupAccess).filter(
                CourseGroupAccess.group_id == group.id,
                CourseGroupAccess.is_active == True
            ).first()
            if course_access:
                lesson_count = db.query(func.count(Lesson.id)).join(Module).filter(
                    Module.course_id == course_access.course_id
                ).scalar()
                if lesson_count:
                    course_max_week = (lesson_count + 4) // 5 # Round up
            
            # Final max_week logic:
            # - Always show up to last scheduled event
            # - Always show up to course length
            # - If active, show up to current week
            potential_max = max(max_content_week, course_max_week)
            if group.is_active:
                potential_max = max(potential_max, calendar_week)
            
            current_week = min(calendar_week, potential_max)
            max_week = min(potential_max, 52) # Hard cap 52

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
            is_active=group.is_active,
            current_week=current_week,
            max_week=max_week
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

    # 1.5 Determine Week Start Date & Date Range
    from src.schemas.models import Event, EventGroup, LessonSchedule
    
    first_ev = db.query(Event).join(EventGroup).filter(
        EventGroup.group_id == group_id,
        Event.event_type == 'class',
        Event.is_active == True
    ).order_by(Event.start_datetime.asc()).first()
    
    start_week1 = None
    if first_ev:
        start_week1 = first_ev.start_datetime.date()
    else:
        first_sc = db.query(LessonSchedule).filter(
            LessonSchedule.group_id == group_id,
            LessonSchedule.is_active == True
        ).order_by(LessonSchedule.scheduled_at.asc()).first()
        if first_sc:
            start_week1 = first_sc.scheduled_at.date()
            
    week_start_dt = None
    week_end_dt = None
    if start_week1:
        start_of_week1 = start_week1 - timedelta(days=start_week1.weekday())
        w_start_date = start_of_week1 + timedelta(weeks=week_number - 1)
        w_end_date = w_start_date + timedelta(days=7)
        week_start_dt = datetime.combine(w_start_date, datetime.min.time())
        week_end_dt = datetime.combine(w_end_date, datetime.min.time())

    # 2. Key logic: Map Week Number to Lesson IDs using LessonSchedule
    # Filter by date range if available to ensure correct calendar display
    if week_start_dt and week_end_dt:
        raw_schedules = db.query(LessonSchedule).filter(
            LessonSchedule.group_id == group_id,
            LessonSchedule.is_active == True,
            LessonSchedule.scheduled_at >= week_start_dt,
            LessonSchedule.scheduled_at < week_end_dt
        ).order_by(LessonSchedule.scheduled_at).all()
    else:
        raw_schedules = db.query(LessonSchedule).filter(
            LessonSchedule.group_id == group_id,
            LessonSchedule.week_number == week_number,
            LessonSchedule.is_active == True
        ).order_by(LessonSchedule.scheduled_at).all()
    
    # Deduplicate by time signature
    schedules = []
    seen_times = set()
    for s in raw_schedules:
        time_sig = s.scheduled_at.replace(second=0, microsecond=0)
        if time_sig not in seen_times:
            schedules.append(s)
            seen_times.add(time_sig)
    
    homework_data = {} # {student_id: {schedule_id: score}}
    attendance_data = {} # {student_id: {schedule_id: score}}
    
    scheduled_lesson_ids = []
    
    if schedules:
        # Use Dynamic Schedule Logic
        scheduled_lesson_ids = [s.lesson_id for s in schedules]
        schedule_map = {s.id: s for s in schedules}
        schedule_ids = [s.id for s in schedules]
        
        # Get Assignments for these lessons (by lesson_id OR event_id)
        from sqlalchemy import or_
        assignments = db.query(Assignment).filter(
            or_(
                Assignment.lesson_id.in_(scheduled_lesson_ids),
                Assignment.event_id.in_(schedule_ids)
            ),
            Assignment.is_active == True
        ).all()
        
        assignment_ids = [a.id for a in assignments]
        
        # Create map: assignment_id -> list of schedule indices (1-based)
        assignment_to_schedule_indices = {}
        
        for a in assignments:
            assignment_to_schedule_indices[a.id] = []
            
            # 1. Check event_id match (Specific Schedule)
            if a.event_id in schedule_ids:
                # Find which schedule index confirms to this event_id
                for idx, s in enumerate(schedules):
                    if s.id == a.event_id:
                        assignment_to_schedule_indices[a.id].append(idx + 1)
            
            # 2. Check lesson_id match (Generic Lesson) - ONLY if not matched by event_id? 
            # Or add both? User said "based on event_id", implying specificity.
            # Let's include lesson_id matches too, but event_id matches are more precise.
            # The previous logic relied on lesson_id.
            if a.lesson_id:
                for idx, s in enumerate(schedules):
                    if s.lesson_id == a.lesson_id:
                         # Avoid adding duplicates if event_id already covered it (unlikely but safe)
                         if (idx + 1) not in assignment_to_schedule_indices[a.id]:
                             assignment_to_schedule_indices[a.id].append(idx + 1)

        # Get Submissions
        submissions = db.query(AssignmentSubmission).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids),
            AssignmentSubmission.user_id.in_(student_ids),
            AssignmentSubmission.is_graded == True
        ).all()
        
        for sub in submissions:
            indices = assignment_to_schedule_indices.get(sub.assignment_id, [])
            for idx in indices:
                if sub.user_id not in homework_data:
                    homework_data[sub.user_id] = {}
                # Store score. If multiple assignments map to same slot, last one wins (or logic could avg)
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

    # 3.5 FETCH SAT DATA
    from src.services.sat_service import SATService
    sat_results_map = {} # user_id -> combinedScore
    
    if week_start_dt and week_end_dt:
        emails = [s.email.lower() for s in students if s.email]
        if emails:
            batch_data = await SATService.fetch_batch_test_results(emails)
            results = batch_data.get("results", [])
            email_to_id = {s.email.lower(): s.id for s in students if s.email}
            for res in results:
                email = res.get("email", "").lower()
                sid = email_to_id.get(email)
                if sid and res.get("data"):
                    pct = SATService.get_percentage_for_week(res["data"], week_start_dt, week_end_dt)
                    if pct is not None:
                        sat_results_map[sid] = pct

    # 4. Construct Response
    result = []
    
    for student_id in student_ids:
        student = students_map.get(student_id)
        if not student: 
            continue
            
        entry = entries_map.get(student_id)
        hw_scores = homework_data.get(student_id, {})
        att_scores = attendance_data.get(student_id, {})
        
        # Priority for mock_exam: SAT Platform data for this week > Manual Entry
        sat_score = sat_results_map.get(student_id)
        mock_exam_score = sat_score if sat_score is not None else (entry.mock_exam if entry else 0)

        # Manual scores defaults
        manual = {
            "curator_hour": entry.curator_hour if entry else 0,
            "mock_exam": mock_exam_score,
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

@router.post("/config", response_model=LeaderboardConfigSchema)
async def update_leaderboard_config(
    payload: LeaderboardConfigUpdateSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Create or update leaderboard column visibility settings for a group/week"""
    import logging
    logger = logging.getLogger(__name__)
    
    # 1. Authorization
    # 1. Authorization
    if current_user.role == "curator":
        group = db.query(Group).filter(Group.id == payload.group_id, Group.curator_id == current_user.id).first()
        if not group:
            raise HTTPException(status_code=403, detail="Access denied to this group")
    elif current_user.role in ["admin", "head_curator"]:
        pass
    else:
        raise HTTPException(status_code=403, detail="Access denied")
    
    logger.warning(f"Received config update: {payload.model_dump()}")
    
    # 2. Get or create config
    config = db.query(LeaderboardConfig).filter(
        LeaderboardConfig.group_id == payload.group_id,
        LeaderboardConfig.week_number == payload.week_number
    ).first()
    
    if not config:
        logger.warning(f"Creating new config for group {payload.group_id}, week {payload.week_number}")
        config = LeaderboardConfig(
            group_id=payload.group_id,
            week_number=payload.week_number
        )
        db.add(config)
    else:
        logger.warning(f"Updating existing config ID {config.id}")
    
    # 3. Update fields
    update_data = payload.model_dump(exclude_unset=True)
    logger.warning(f"Update data (exclude_unset): {update_data}")
    
    for field, value in update_data.items():
        if field not in ["group_id", "week_number"] and hasattr(config, field):
            old_value = getattr(config, field)
            setattr(config, field, value)
            logger.warning(f"Updated {field}: {old_value} -> {value}")
            
    db.commit()
    db.refresh(config)
    
    logger.warning(f"Final config state: curator_hour_enabled={config.curator_hour_enabled}, study_buddy_enabled={config.study_buddy_enabled}")
    
    return config

@router.get("/curator/weekly-lessons/{group_id}")
async def get_weekly_lessons_with_hw_status(
    group_id: int,
    week_number: int = Query(..., ge=1, le=52),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get weekly lessons (Events) with homework status for leaderboards.
    Dynamically assumes the group's first event is Week 1.
    """
    # 1. Authorization
    # 1. Authorization
    if current_user.role == "curator":
        group = db.query(Group).filter(Group.id == group_id, Group.curator_id == current_user.id).first()
        if not group:
            raise HTTPException(status_code=403, detail="Access denied to this group")
    elif current_user.role in ["admin", "head_curator"]:
        pass
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    # 1.5 Get Leaderboard Config
    config = db.query(LeaderboardConfig).filter(
        LeaderboardConfig.group_id == group_id,
        LeaderboardConfig.week_number == week_number
    ).first()
    
    # Default config if not exists
    if not config:
        config_data = {
            "extra_points_enabled": True,
            "curator_hour_date": None
        }
    else:
        config_data = {
            "extra_points_enabled": config.extra_points_enabled,
            "curator_hour_date": config.curator_hour_date
        }

    # 2. Determine Week Start Date based on first event OR first schedule
    # Logic: Find earliest event for this group -> that is start of Week 1
    # Week N start = Earliest + (N-1)*7 days
    from src.schemas.models import Event, EventGroup, LessonSchedule
    
    first_event = db.query(Event).join(EventGroup).filter(
        EventGroup.group_id == group_id,
        Event.event_type == 'class',
        Event.is_active == True
    ).order_by(Event.start_datetime.asc()).first()
    
    week_start_date = None
    week_end_date = None
    events = []
    mode = "event"
    seen_times = set()

    # Determine Week 1 Start
    start_of_week1 = None
    if first_event:
        start_of_week1 = first_event.start_datetime.date()
    else:
        first_sched_any = db.query(LessonSchedule).filter(
            LessonSchedule.group_id == group_id,
            LessonSchedule.is_active == True
        ).order_by(LessonSchedule.scheduled_at.asc()).first()
        if first_sched_any:
            start_of_week1 = first_sched_any.scheduled_at.date()
            
    if start_of_week1:
        # Align to Monday
        start_of_week1 = start_of_week1 - timedelta(days=start_of_week1.weekday())
        week_start_date = start_of_week1 + timedelta(weeks=week_number - 1)
        week_end_date = week_start_date + timedelta(days=7)
    
        # 3. Get Events for this week
        from src.services.event_service import EventService
        from src.schemas.models import CourseGroupAccess, EventCourse
        
        course_accesses = db.query(CourseGroupAccess).filter(
            CourseGroupAccess.group_id == group_id,
            CourseGroupAccess.is_active == True
        ).all()
        course_ids = [ca.course_id for ca in course_accesses]
        
        week_end_dt = datetime.combine(week_end_date, datetime.min.time())
        week_start_dt = datetime.combine(week_start_date, datetime.min.time())
        
        # Standard events
        standard_events = db.query(Event).outerjoin(EventGroup).outerjoin(EventCourse).filter(
            Event.event_type == 'class',
            Event.is_active == True,
            Event.start_datetime >= week_start_dt,
            Event.start_datetime < week_end_dt,
            Event.is_recurring == False,
            or_(
                EventGroup.group_id == group_id,
                EventCourse.course_id.in_(course_ids)
            )
        ).distinct().order_by(Event.start_datetime).all()
        
        # Recurring events
        recurring_instances = EventService.expand_recurring_events(
            db=db,
            start_date=week_start_dt,
            end_date=week_end_dt - timedelta(seconds=1),
            group_ids=[group_id],
            course_ids=course_ids
        )
        recurring_instances = [e for e in recurring_instances if e.event_type == 'class']
        
        for e in standard_events:
            time_sig = e.start_datetime.replace(second=0, microsecond=0)
            if time_sig not in seen_times:
                e.is_pseudo = False
                events.append(e)
                seen_times.add(time_sig)
                
        for instance in recurring_instances:
            time_sig = instance.start_datetime.replace(second=0, microsecond=0)
            if time_sig not in seen_times:
                instance.is_pseudo = False
                events.append(instance)
                seen_times.add(time_sig)
    
        # 4. Merge LessonSchedule for the current week
        # Filter by date range instead of week_number to avoid cross-week display
        schedules = db.query(LessonSchedule).filter(
            LessonSchedule.group_id == group_id,
            LessonSchedule.is_active == True,
            LessonSchedule.scheduled_at >= week_start_dt,
            LessonSchedule.scheduled_at < week_end_dt
        ).order_by(LessonSchedule.scheduled_at).all()
        
        for sched in schedules:
            time_sig = sched.scheduled_at.replace(second=0, microsecond=0)
            if time_sig not in seen_times:
                lesson_title = sched.lesson.title if sched.lesson else f"Lesson {sched.id}"
                pseudo_event = Event(
                    id=sched.id,
                    title=lesson_title,
                    start_datetime=sched.scheduled_at,
                    event_type='class'
                )
                pseudo_event.lesson_id = sched.lesson_id
                pseudo_event.is_pseudo = True
                pseudo_event.schedule_id = sched.id
                events.append(pseudo_event)
                seen_times.add(time_sig)

    events.sort(key=lambda x: x.start_datetime)
                
    if not events:
         return {"week_number": week_number, "week_start": week_start_date or datetime.utcnow(), "lessons": [], "students": []}
         
    if not week_start_date:
         week_start_date = datetime.utcnow() # Warning: Should not happen if events exist
    
    # 4. Get Assignments linked
    event_homework_map = {}
    
    # Process event types
    real_event_ids = [e.id for e in events if not getattr(e, 'is_pseudo', False)]
    lesson_ids = [e.lesson_id for e in events if hasattr(e, 'lesson_id') and e.lesson_id is not None]
    
    # Query assignments by event_id OR lesson_id
    query_filters = []
    if real_event_ids:
        query_filters.append(Assignment.event_id.in_(real_event_ids))
    if lesson_ids:
        query_filters.append(Assignment.lesson_id.in_(lesson_ids))
    
    if query_filters:
        assignments = db.query(Assignment).filter(
            or_(*query_filters),
            Assignment.is_active == True
        ).all()
        
        # Priority: Event-specific assignment > Lesson-specific assignment
        
        # First, map by lesson_id (base)
        lesson_assignment_map = {}
        for a in assignments:
            if a.lesson_id:
                 lesson_assignment_map[a.lesson_id] = a
    
        # Then map by event_id (override/specific)
        event_specific_map = {}
        for a in assignments:
            if a.event_id:
                event_specific_map[a.event_id] = a
                
        # Now populate event_homework_map
        for e in events:
            # Check specific event assignment first (ONLY for real events)
            if not getattr(e, 'is_pseudo', False) and e.id in event_specific_map:
                event_homework_map[e.id] = event_specific_map[e.id]
            # Check lesson assignment
            elif hasattr(e, 'lesson_id') and e.lesson_id and e.lesson_id in lesson_assignment_map:
                event_homework_map[e.id] = lesson_assignment_map[e.lesson_id]
    
        # Collect final assignment IDs for submission lookup
        assignment_ids = list(set([a.id for a in event_homework_map.values()]))
    else:
        assignment_ids = []
    
    # 5. Build Lesson Columns metadata
    lessons_meta = []
    for idx, event in enumerate(events):
        hw = event_homework_map.get(event.id)
        lessons_meta.append({
            "lesson_number": idx + 1,
            "event_id": event.id,
            "title": event.title,
            "start_datetime": event.start_datetime,
            "homework": {
                "id": hw.id,
                "title": hw.title
            } if hw else None
        })
        
    # 6. Get Students
    group_students = db.query(GroupStudent).filter(GroupStudent.group_id == group_id).all()
    student_ids = [gs.student_id for gs in group_students]
    
    if not student_ids:
        return {
            "week_number": week_number, 
            "week_start": week_start_date, 
            "lessons": lessons_meta, 
            "students": [],
            "config": config_data
        }
        
    students = db.query(UserInDB).filter(UserInDB.id.in_(student_ids)).all()
    students_list = sorted(students, key=lambda s: s.name or "")
    
    # 7. Get Attendance
    # Need to check EventParticipant table
    from src.schemas.models import EventParticipant
    
    attendance_map = {}
    
    # 7.1 Real Events (EventParticipant)
    if real_event_ids:
        event_attendances = db.query(EventParticipant).filter(
            EventParticipant.event_id.in_(real_event_ids),
            EventParticipant.user_id.in_(student_ids)
        ).all()
        # Map (user_id, event_id) -> status
        for a in event_attendances:
            attendance_map[(a.user_id, a.event_id)] = a.registration_status
            
    # 7.2 Pseudo Events (Attendance from LessonSchedule)
    schedule_ids = [e.schedule_id for e in events if getattr(e, 'is_pseudo', False) and hasattr(e, 'schedule_id')]
    if schedule_ids:
        sched_attendances = db.query(Attendance).filter(
            Attendance.lesson_schedule_id.in_(schedule_ids),
            Attendance.user_id.in_(student_ids)
        ).all()
        
        # Map (user_id, schedule_id) -> status
        # Note: Event ID in events list for pseudo event IS schedule_id
        for a in sched_attendances:
            status = "attended" if a.score > 0 else "absent"
            attendance_map[(a.user_id, a.lesson_schedule_id)] = status

    
    # 8. Get HW Submissions
    submission_map = {}
    if assignment_ids:
        submissions = db.query(AssignmentSubmission).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids),
            AssignmentSubmission.user_id.in_(student_ids)
        ).all()
        # Map (user_id, assignment_id) -> submission
        submission_map = {(s.user_id, s.assignment_id): s for s in submissions}
    
    # 9. Get Manual Leaderboard Entries
    manual_entries = db.query(LeaderboardEntry).filter(
        LeaderboardEntry.group_id == group_id,
        LeaderboardEntry.week_number == week_number
    ).all()
    manual_map = {e.user_id: e for e in manual_entries}

    # 9.5 FETCH SAT DATA
    from src.services.sat_service import SATService
    sat_results_map = {} # user_id -> combinedScore
    
    if student_ids and week_start_date and week_end_date:
        emails = [s.email.lower() for s in students_list if s.email]
        if emails:
            # Fetch all results for these emails
            batch_data = await SATService.fetch_batch_test_results(emails)
            results = batch_data.get("results", [])
            
            # Map email -> data
            email_to_id = {s.email.lower(): s.id for s in students_list if s.email}
            
            # Convert dates to datetime for get_score_for_week
            w_start = datetime.combine(week_start_date, datetime.min.time())
            w_end = datetime.combine(week_end_date, datetime.min.time())
            
            for res in results:
                email = res.get("email", "").lower()
                student_id = email_to_id.get(email)
                if student_id and res.get("data"):
                    pct = SATService.get_percentage_for_week(res["data"], w_start, w_end)
                    if pct is not None:
                        sat_results_map[student_id] = pct

    # 10. Build Student Rows
    student_rows = []
    for student in students_list:
        # Get manual entry
        manual = manual_map.get(student.id)
        
        # Priority for mock_exam: SAT Platform data for this week > Manual Entry
        sat_score = sat_results_map.get(student.id)
        mock_exam_score = sat_score if sat_score is not None else (manual.mock_exam if manual else 0)

        manual_data = {
            "curator_hour": manual.curator_hour if manual else 0,
            "mock_exam": mock_exam_score,
            "study_buddy": manual.study_buddy if manual else 0,
            "self_reflection_journal": manual.self_reflection_journal if manual else 0,
            "weekly_evaluation": manual.weekly_evaluation if manual else 0,
            "extra_points": manual.extra_points if manual else 0,
        }

        lesson_data = {}
        for idx, event in enumerate(events):
            # Attendance
            # Default to "registered" if event exists? No, default absent if not in participant table?
            # Actually, EventParticipant is usually created when they register/attend.
            # If nothing, assumption: missed.
            status = attendance_map.get((student.id, event.id), "missed") 
            
            # Homework
            hw = event_homework_map.get(event.id)
            hw_status = None
            if hw:
                sub = submission_map.get((student.id, hw.id))
                if sub:
                    hw_status = {
                        "submitted": True,
                        "score": sub.score,
                        "max_score": sub.max_score,
                        "is_graded": sub.is_graded,
                        "submission_id": sub.id
                    }
                else:
                    hw_status = {"submitted": False, "score": None}
            
            lesson_data[str(idx + 1)] = {
                "event_id": event.id,
                "attendance_status": status,
                "homework_status": hw_status
            }
            
        student_rows.append({
            "student_id": student.id,
            "student_name": student.name,
            "avatar_url": student.avatar_url,
            "lessons": lesson_data,
            **manual_data
        })
        
    return {
        "week_number": week_number,
        "week_start": week_start_date,
        "lessons": lessons_meta,
        "students": student_rows,
        "config": config_data
    }

@router.get("/curator/full-attendance/{group_id}")
async def get_group_full_attendance_matrix(
    group_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get full attendance matrix for a group (all lessons).
    Handles standard events and expanded recurring schedules.
    """
    # 1. Authorization & Group Info
    group_obj = db.query(Group).filter(Group.id == group_id).first()
    if not group_obj:
        raise HTTPException(status_code=404, detail="Group not found")

    if current_user.role == "curator":
        if group_obj.curator_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied to this group (Curator mismatch)")
    elif current_user.role == "teacher":
        if group_obj.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied to this group (Teacher mismatch)")
    elif current_user.role == "admin":
        pass
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    # 2. Get Group Creation Date and Linked Courses
    from src.schemas.models import Event, EventGroup, EventParticipant, LessonSchedule, CourseGroupAccess, EventCourse
    
    creation_date = group_obj.created_at if group_obj else datetime.utcnow() - timedelta(days=90)
    
    # Find courses linked to this group
    course_accesses = db.query(CourseGroupAccess).filter(CourseGroupAccess.group_id == group_id, CourseGroupAccess.is_active == True).all()
    course_ids = [ca.course_id for ca in course_accesses]
    
    # 3. Fetch Standard Events (Group-linked OR Course-linked)
    standard_events_query = db.query(Event).outerjoin(EventGroup).outerjoin(EventCourse).filter(
        Event.event_type == 'class',
        Event.is_active == True,
        Event.is_recurring == False,
        or_(
            EventGroup.group_id == group_id,
            EventCourse.course_id.in_(course_ids)
        )
    ).distinct()
    standard_events = standard_events_query.order_by(Event.start_datetime.asc()).all()

    # 4. Expand Recurring Events (Group-linked OR Course-linked)
    from src.services.event_service import EventService
    
    start_search = datetime.utcnow() - timedelta(days=365)
    end_search = datetime.utcnow() + timedelta(days=365)
    
    recurring_instances = EventService.expand_recurring_events(
        db=db,
        start_date=start_search,
        end_date=end_search,
        group_ids=[group_id],
        course_ids=course_ids
    )
    
    recurring_instances = [e for e in recurring_instances if e.event_type == 'class']

    # 5. Combine and Deduplicate
    combined_events = []
    seen_times = set()
    
    # Process standard events
    for e in standard_events:
        time_sig = e.start_datetime.replace(second=0, microsecond=0)
        if time_sig not in seen_times:
            combined_events.append(e)
            seen_times.add(time_sig)
            
    # Process recurring instances
    for instance in recurring_instances:
        time_sig = instance.start_datetime.replace(second=0, microsecond=0)
        if time_sig not in seen_times:
            combined_events.append(instance)
            seen_times.add(time_sig)
            
    all_events = combined_events

    # 6. Always include LessonSchedule to ensure all intended slots are visible
    schedules = db.query(LessonSchedule).filter(
        LessonSchedule.group_id == group_id,
        LessonSchedule.is_active == True
    ).order_by(LessonSchedule.scheduled_at).all()
    
    for sched in schedules:
        time_sig = sched.scheduled_at.replace(second=0, microsecond=0)
        if time_sig not in seen_times:
            lesson_title = sched.lesson.title if sched.lesson else f"Lesson {sched.id}"
            pseudo_event = Event(
                id=sched.id,
                title=lesson_title,
                start_datetime=sched.scheduled_at,
                event_type='class'
            )
            pseudo_event.lesson_id = sched.lesson_id
            all_events.append(pseudo_event)
            seen_times.add(time_sig)

    all_events.sort(key=lambda x: x.start_datetime)

    all_events.sort(key=lambda x: x.start_datetime)

    # 9. Build Lessons Meta
    lessons_meta = []
    for idx, event in enumerate(all_events):
        lessons_meta.append({
            "lesson_number": idx + 1,
            "event_id": event.id,
            "title": event.title,
            "start_datetime": event.start_datetime
        })

    if not all_events:
         return {"lessons": [], "students": []}

    event_ids = [e.id for e in all_events]
    
    # 7. Get Students
    group_students = db.query(GroupStudent).filter(GroupStudent.group_id == group_id).all()
    student_ids = [gs.student_id for gs in group_students]
    
    if not student_ids:
        return {"lessons": lessons_meta, "students": []}
        
    students = db.query(UserInDB).filter(UserInDB.id.in_(student_ids)).all()
    students_list = sorted(students, key=lambda s: s.name or "")

    # 8. Get Attendance
    # Note: For recurring instances, we use their pseudo-IDs (consistent with calendar)
    attendances = db.query(EventParticipant).filter(
        EventParticipant.event_id.in_(event_ids),
        EventParticipant.user_id.in_(student_ids)
    ).all()
    # Map (user_id, event_id) -> status
    attendance_map = {(a.user_id, a.event_id): a.registration_status for a in attendances}

    # 10. Build Student Rows
    student_rows = []
    for student in students_list:
        lesson_data = {}
        for idx, event in enumerate(all_events):
            status = attendance_map.get((student.id, event.id), "missed") 
            lesson_data[str(idx + 1)] = {
                "event_id": event.id,
                "attendance_status": status
            }
            
        student_rows.append({
            "student_id": student.id,
            "student_name": student.name,
            "avatar_url": student.avatar_url,
            "lessons": lesson_data
        })
        
    return {
        "lessons": lessons_meta,
        "students": student_rows
    }

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


@router.get("/curator/leaderboard-full/{group_id}")
async def get_weekly_lessons_with_hw_status(
    group_id: int,
    week_number: int = Query(..., ge=1, le=52),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Enhanced leaderboard endpoint returning structured lessons, homework status, 
    student rows and configuration.
    """
    if current_user.role not in ["curator", "admin", "head_curator"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # 1. Get Group and Schedules
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    schedules = db.query(LessonSchedule).filter(
        LessonSchedule.group_id == group_id,
        LessonSchedule.week_number == week_number,
        LessonSchedule.is_active == True
    ).order_by(LessonSchedule.scheduled_at).all()
    
    lessons_meta = []
    if not schedules:
        # FALLBACK: Legacy Logic (No schedules found)
        # Anchor week start to Group creation or Course start
        # Assume Week 1 starts on the Monday of the week the group was created
        group_base_date = group.created_at or datetime.utcnow()
        # Find the Monday of that week
        week1_start = group_base_date - timedelta(days=group_base_date.weekday())
        week_start = week1_start + timedelta(weeks=week_number - 1)
        
        start_lesson_index = (week_number - 1) * 5
        course_access = db.query(CourseGroupAccess).filter(
            CourseGroupAccess.group_id == group_id,
            CourseGroupAccess.is_active == True
        ).first()

        if course_access:
            lessons_query = db.query(Lesson).join(Module).filter(
                Module.course_id == course_access.course_id
            ).order_by(Module.order_index, Lesson.order_index).offset(start_lesson_index).limit(5).all()
            
            for idx, lesson in enumerate(lessons_query):
                # Find assignment
                assignment = db.query(Assignment).filter(
                    Assignment.lesson_id == lesson.id,
                    Assignment.is_active == True
                ).first()
                
                # Distribute lessons: Mon, Tue, Wed, Thu, Fri
                lesson_date = week_start + timedelta(days=idx)
                
                lessons_meta.append({
                    "lesson_number": idx + 1,
                    "event_id": 0, # No schedule ID
                    "title": lesson.title,
                    "start_datetime": lesson_date.isoformat(),
                    "homework": {
                        "id": assignment.id,
                        "title": assignment.title
                    } if assignment else None
                })
    else:
        week_start = schedules[0].scheduled_at
        for idx, s in enumerate(schedules):
            # Find assignment
            assignment = db.query(Assignment).filter(
                Assignment.lesson_id == s.lesson_id,
                Assignment.is_active == True
            ).first()
            
            lessons_meta.append({
                "lesson_number": idx + 1,
                "event_id": s.id, # We use schedule ID as event_id for attendance tracking
                "title": s.lesson.title if s.lesson else f"Lesson {idx+1}",
                "start_datetime": s.scheduled_at.isoformat(),
                "homework": {
                    "id": assignment.id,
                    "title": assignment.title
                } if assignment else None
            })

    # 2. Get Student Rows
    # Re-use existing get_group_leaderboard logic or similar data
    students_data = await get_group_leaderboard(group_id, week_number, current_user, db)
    
    # 3. Format students for the frontend expected structure
    formatted_students = []
    for row in students_data:
        # Map flat row to structured lessons
        student_lessons = {}
        # We always expect up to 5 lessons in fallback or dynamic
        lessons_count = len(schedules) if schedules else len(lessons_meta)
        
        for i in range(1, 6):
            # Extract HW score
            hw_score = row.get(f"hw_lesson_{i}")
            
            # Extract Attendance
            attendance_status = "absent"
            att_score = row.get(f"lesson_{i}")
            
            if schedules:
                if att_score == 10: attendance_status = "attended"
                elif att_score > 0: attendance_status = "late"
            else:
                # In legacy mode, attendance score IS the lesson score
                if att_score >= 10: attendance_status = "attended"
                elif att_score > 0: attendance_status = "late"
            
            # Find schedule ID for this lesson
            event_id = 0
            if schedules and i <= len(schedules):
                event_id = schedules[i-1].id

            student_lessons[str(i)] = {
                "event_id": event_id,
                "attendance_status": attendance_status,
                "homework_status": {
                    "submitted": hw_score is not None,
                    "score": hw_score
                } if row.get(f"hw_lesson_{i}") is not None else None
            }

        formatted_students.append({
            "student_id": row["student_id"],
            "student_name": row["student_name"],
            "avatar_url": row["avatar_url"],
            "lessons": student_lessons,
            "curator_hour": row["curator_hour"],
            "mock_exam": row["mock_exam"],
            "study_buddy": row["study_buddy"],
            "self_reflection_journal": row["self_reflection_journal"],
            "weekly_evaluation": row["weekly_evaluation"],
            "extra_points": row["extra_points"]
        })

    # 4. Get/Create Config
    config = db.query(LeaderboardConfig).filter(
        LeaderboardConfig.group_id == group_id,
        LeaderboardConfig.week_number == week_number
    ).first()
    
    if not config:
        config = LeaderboardConfig(
            group_id=group_id,
            week_number=week_number
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    return {
        "week_number": week_number,
        "week_start": week_start.isoformat(),
        "lessons": lessons_meta,
        "students": formatted_students,
        "config": {
            "curator_hour_enabled": config.curator_hour_enabled,
            "study_buddy_enabled": config.study_buddy_enabled,
            "self_reflection_journal_enabled": config.self_reflection_journal_enabled,
            "weekly_evaluation_enabled": config.weekly_evaluation_enabled,
            "extra_points_enabled": config.extra_points_enabled,
            "curator_hour_date": config.curator_hour_date
        }
    }


@router.post("/curator/leaderboard-config")
async def update_leaderboard_config(
    data: LeaderboardConfigUpdateSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Update or create leaderboard configuration."""
    if current_user.role not in ["curator", "admin", "head_curator"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    config = db.query(LeaderboardConfig).filter(
        LeaderboardConfig.group_id == data.group_id,
        LeaderboardConfig.week_number == data.week_number
    ).first()

    if config:
        for field, value in data.dict(exclude_unset=True).items():
            if field not in ['group_id', 'week_number']:
                setattr(config, field, value)
    else:
        config = LeaderboardConfig(**data.dict())
        db.add(config)
    
    db.commit()
    db.refresh(config)
    return config

class AttendanceInputSchema(BaseModel):
    group_id: int
    week_number: int
    lesson_index: int # 1-5
    student_id: int
    score: int
    status: str = "present"
    event_id: Optional[int] = None

class BulkAttendanceInputSchema(BaseModel):
    updates: List[AttendanceInputSchema]

@router.post("/curator/attendance/bulk")
async def update_attendance_bulk(
    data: BulkAttendanceInputSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Update multiple attendance records in a single transaction.
    Supports event-based updates (preferred) and legacy schedule-based updates.
    """
    if current_user.role not in ["curator", "admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Access denied")

    from src.schemas.models import EventParticipant, Attendance
    from src.services.event_service import EventService

    updated_count = 0
    cached_groups = {} # id -> group_obj

    for item in data.updates:
        # Auth check
        if item.group_id not in cached_groups:
            group = db.query(Group).filter(Group.id == item.group_id).first()
            if not group: continue
            
            # Role-based restriction
            if current_user.role == "curator" and group.curator_id != current_user.id: continue
            if current_user.role == "teacher" and group.teacher_id != current_user.id: continue
            cached_groups[item.group_id] = group

        # Priority: event_id
        if item.event_id:
            real_event_id = EventService.resolve_event_id(db, item.event_id)
            if not real_event_id: continue

            participant = db.query(EventParticipant).filter(
                EventParticipant.event_id == real_event_id,
                EventParticipant.user_id == item.student_id
            ).first()

            status = item.status
            # Map legacy status if needed or stick to what frontend sends
            # Logic from single update: "attended" if score > 0 else "absent"
            # But frontend sends 'attended', 'late', 'missed'
            
            if participant:
                participant.registration_status = status
                participant.attended_at = datetime.utcnow() if status != 'missed' else None
            else:
                participant = EventParticipant(
                    event_id=real_event_id,
                    user_id=item.student_id,
                    registration_status=status,
                    attended_at=datetime.utcnow() if status != 'missed' else None
                )
                db.add(participant)
            updated_count += 1
            continue

        # Fallback: Schedule-based (Legacy)
        schedules = db.query(LessonSchedule).filter(
            LessonSchedule.group_id == item.group_id,
            LessonSchedule.week_number == item.week_number,
            LessonSchedule.is_active == True
        ).order_by(LessonSchedule.scheduled_at).all()

        if schedules and 0 < item.lesson_index <= len(schedules):
            target_schedule = schedules[item.lesson_index - 1]
            attendance = db.query(Attendance).filter(
                Attendance.lesson_schedule_id == target_schedule.id,
                Attendance.user_id == item.student_id
            ).first()

            if attendance:
                attendance.score = item.score
                attendance.status = item.status
            else:
                attendance = Attendance(
                    lesson_schedule_id=target_schedule.id,
                    user_id=item.student_id,
                    score=item.score,
                    status=item.status
                )
                db.add(attendance)
            updated_count += 1

    db.commit()
    return {"status": "success", "updated_count": updated_count}

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
    if current_user.role not in ["curator", "admin", "head_curator", "teacher"]:
        raise HTTPException(status_code=403, detail="Access denied")
        
    group = db.query(Group).filter(Group.id == data.group_id).first()
    if not group:
         raise HTTPException(status_code=404, detail="Group not found")
         
    if current_user.role == "curator" and group.curator_id != current_user.id:
         raise HTTPException(status_code=403, detail="Access denied to this group (Curator mismatch)")
         
    if current_user.role == "teacher" and group.teacher_id != current_user.id:
         raise HTTPException(status_code=403, detail="Access denied to this group (Teacher mismatch)")

    # Mode 1: Event-based (New)
    if data.event_id:
        from src.services.event_service import EventService
        from src.schemas.models import EventParticipant
        
        # Ensure event exists (materialize if pseudo-id)
        real_event_id = EventService.resolve_event_id(db, data.event_id)
        if not real_event_id:
             raise HTTPException(status_code=404, detail="Event could not be resolved/materialized")

        participant = db.query(EventParticipant).filter(
            EventParticipant.event_id == real_event_id,
            EventParticipant.user_id == data.student_id
        ).first()
        
        if participant:
            participant.registration_status = "attended" if data.score > 0 else "absent"
            participant.attended_at = datetime.utcnow() if data.score > 0 else None
        else:
            participant = EventParticipant(
                event_id=real_event_id,
                user_id=data.student_id,
                registration_status="attended" if data.score > 0 else "absent",
                attended_at=datetime.utcnow() if data.score > 0 else None
            )
            db.add(participant)
        
        db.commit()
        return {"status": "success", "mode": "event", "event_id": real_event_id}

    # Mode 2: Schedule-based (Legacy/Generated)
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
    lessons_count: Optional[int] = None

class GroupScheduleResponse(BaseModel):
    start_date: date
    weeks_count: int
    lessons_count: Optional[int] = None
    schedule_items: List[ScheduleItem]


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
    if current_user.role not in ["curator", "admin", "head_curator"]:
       raise HTTPException(status_code=403, detail="Access denied")

    # Fetch group and course
    from src.schemas.models import CourseGroupAccess
    
    course_access = db.query(CourseGroupAccess).filter(
        CourseGroupAccess.group_id == data.group_id,
        CourseGroupAccess.is_active == True
    ).first()
    
    group = db.query(Group).filter(Group.id == data.group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    if not course_access:
        raise HTTPException(status_code=400, detail="Group has no active course")
        
    # Fetch all lessons
    lessons = db.query(Lesson).join(Module).filter(
        Module.course_id == course_access.course_id
    ).order_by(Module.order_index, Lesson.order_index).all()
    
    if not lessons:
        raise HTTPException(status_code=400, detail="Course has no lessons")

    # Parse times
    # schedule_items = [{day_of_week: 0, time_of_day: "19:00"}, ...]
    
    # CLEANUP: Deactivate existing active schedules for this group to avoid duplicates
    # 1. Legacy LessonSchedules
    existing_schedules = db.query(LessonSchedule).filter(
        LessonSchedule.group_id == data.group_id,
        LessonSchedule.is_active == True
    ).all()
    
    for old_sched in existing_schedules:
        old_sched.is_active = False
        # Also deactivate linked assignments
        old_assignments = db.query(GroupAssignment).filter(
            GroupAssignment.lesson_schedule_id == old_sched.id,
            GroupAssignment.is_active == True
        ).all()
        for oa in old_assignments:
            oa.is_active = False
            
    # 2. Existing Recurring Events (of type 'class' created by generator)
    # We identify them by group link and type.
    # To be safe, we only deactivate events that look like "Online Class" or are recurring classes for this group
    # during the target period? Or just all recurring classes?
    # User wants a clean slate. Let's deactivate all ACTIVE RECURRING class events for this group.
    
    existing_events = db.query(Event).join(EventGroup).filter(
        EventGroup.group_id == data.group_id,
        Event.event_type == 'class',
        Event.is_recurring == True,
        Event.is_active == True
    ).all()
    
    for e in existing_events:
        e.is_active = False
            
    db.flush()

    # Generate NEW Schedule (Recurring Events)
    # Instead of creating 100 individual events, we create 1 recurring event per Weekly Slot.
    # e.g. Mon 19:00 -> 1 Recurring Event (Weekly)
    
    # Calculate duration
    if data.lessons_count and data.schedule_items:
        import math
        # Frequency = count of lessons per week
        frequency = len(data.schedule_items)
        # Duration in weeks = lessons / frequency
        # Note: This is an approximation for recurring events end_date
        week_limit = math.ceil(data.lessons_count / frequency)
    else:
        week_limit = data.weeks_count
        
    start_date = data.start_date
    end_recurrence = start_date + timedelta(weeks=week_limit)
    
    generated_count = 0
    
    for item in data.schedule_items:
        # Find first occurrence of this day after/on start_date
        # item.day_of_week: 0=Mon, 6=Sun
        
        # Parse time
        try:
            time_obj = datetime.strptime(item.time_of_day, "%H:%M").time()
        except ValueError:
            continue
            
        # Calculate first date
        days_ahead = item.day_of_week - start_date.weekday()
        if days_ahead < 0:
            days_ahead += 7
        
        first_date = start_date + timedelta(days=days_ahead)
        start_dt = datetime.combine(first_date, time_obj)
        end_dt = start_dt + timedelta(minutes=90) # Default 1.5h
        
        # Check if an event already exists for this group at this time
        existing_event = db.query(Event).join(EventGroup).filter(
            EventGroup.group_id == data.group_id,
            Event.start_datetime == start_dt,
            Event.is_active == True
        ).first()
        
        if existing_event:
            # Skip creating duplicate event
            continue
        
        # Create Recurring Event
        event = Event(
            title=f"{group.name}: Online Class",
            description="Regular scheduled class via Zoom",
            event_type="class",
            start_datetime=start_dt,
            end_datetime=end_dt,
            location="Online (Scheduled)",
            is_online=True,
            meeting_url="",
            created_by=current_user.id,
            is_active=True,
            is_recurring=True,
            recurrence_pattern="weekly",
            recurrence_end_date=end_recurrence,
            max_participants=50
        )
        db.add(event)
        db.flush()
        
        # Link to group
        event_group = EventGroup(
            event_id=event.id,
            group_id=data.group_id
        )
        db.add(event_group)
        
        generated_count += 1
            
    # Also generate individual LessonSchedule entries for leaderboard tracking
    # (These will be hidden in calendar by deduplication if real events exist)
    lessons_scheduled = 0
    total_lessons = data.lessons_count if data.lessons_count else (len(data.schedule_items) * week_limit)
    
    for week in range(week_limit):
        for item in data.schedule_items:
            if lessons_scheduled >= total_lessons:
                break
                
            if lessons_scheduled >= len(lessons):
                break
                
            lesson = lessons[lessons_scheduled]
            
            # Find date for this week and day
            try:
                time_obj = datetime.strptime(item.time_of_day, "%H:%M").time()
            except ValueError:
                time_obj = datetime.min.time()
                
            days_ahead = item.day_of_week - start_date.weekday()
            if days_ahead < 0:
                days_ahead += 7
            
            target_date = start_date + timedelta(weeks=week, days=days_ahead)
            target_dt = datetime.combine(target_date, time_obj)
            
            # Check if schedule already exists for this group at this time
            existing = db.query(LessonSchedule).filter(
                LessonSchedule.group_id == data.group_id,
                LessonSchedule.scheduled_at == target_dt,
                LessonSchedule.is_active == True
            ).first()
            
            if not existing:
                new_sched = LessonSchedule(
                    group_id=data.group_id,
                    lesson_id=lesson.id,
                    week_number=week + 1,
                    scheduled_at=target_dt,
                    is_active=True
                )
                db.add(new_sched)
            lessons_scheduled += 1

    # Save config for future use
    group.schedule_config = {
        "start_date": data.start_date.isoformat(),
        "weeks_count": week_limit,
        "lessons_count": total_lessons,
        "schedule_items": [item.dict() for item in data.schedule_items]
    }
    db.commit()
    
    return {"message": f"Schedule generated successfully. Created {generated_count} recurring event series and {lessons_scheduled} planned lessons."}

@router.get("/curator/schedule/{group_id}", response_model=GroupScheduleResponse)
async def get_group_schedule(
    group_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Fetch existing recurring schedule for a group.
    """
    if current_user.role not in ["curator", "admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Access denied")
        
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
         raise HTTPException(status_code=404, detail="Group not found")
         
    if current_user.role == "teacher" and group.teacher_id != current_user.id:
         raise HTTPException(status_code=403, detail="Access denied to this group schedule")
        
    # Find active recurring events for this group
    # Try to return saved config first (more accurate)
    if group.schedule_config:
        config = group.schedule_config
        return {
            "start_date": config.get("start_date"),
            "weeks_count": config.get("weeks_count", 12),
            "lessons_count": config.get("lessons_count"),
            "schedule_items": config.get("schedule_items", [])
        }

    events = db.query(Event).join(EventGroup).filter(
        EventGroup.group_id == group_id,
        Event.event_type == 'class',
        Event.is_recurring == True,
        Event.is_active == True
    ).all()
    
    if not events:
        # Fallback to defaults or return empty
        return {
            "start_date": date.today(),
            "weeks_count": 12,
            "lessons_count": 48,
            "schedule_items": []
        }
        
    # Reconstruct schedule items
    schedule_items = []
    min_start_date = events[0].start_datetime.date()
    max_end_date = events[0].recurrence_end_date or date.today()
    
    for event in events:
        start_date_only = event.start_datetime.date()
        if start_date_only < min_start_date:
            min_start_date = start_date_only
        
        if event.recurrence_end_date and event.recurrence_end_date > max_end_date:
            max_end_date = event.recurrence_end_date
            
        schedule_items.append({
            "day_of_week": event.start_datetime.weekday(),
            "time_of_day": event.start_datetime.strftime("%H:%M")
        })
        
    # Calculate weeks count
    weeks_count = 12
    if min_start_date and max_end_date:
        days_diff = (max_end_date - min_start_date).days
        weeks_count = max(1, (days_diff // 7))
    
    return {
        "start_date": min_start_date,
        "weeks_count": weeks_count,
        "lessons_count": weeks_count * len(schedule_items),
        "schedule_items": schedule_items
    }


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
    
    if current_user.role not in ['student', 'admin', 'head_curator']:
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
