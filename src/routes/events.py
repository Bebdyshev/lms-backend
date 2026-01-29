from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, and_, or_, select
from typing import List, Optional
from datetime import datetime, date, timedelta

from src.config import get_db
from src.schemas.models import (
    UserInDB, Event, EventGroup, EventParticipant, Group, GroupStudent,
    EventSchema, EventParticipantSchema, Enrollment, EventCourse, Course,
    CreateEventRequest, Assignment, Lesson, Module, LessonSchedule
)
from src.routes.auth import get_current_user_dependency
from src.utils.permissions import require_role

router = APIRouter()

@router.get("/my", response_model=List[EventSchema])
async def get_my_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    event_type: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    upcoming_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Get events for current user based on their groups"""
    
    # Get user's groups and courses
    user_group_ids = []
    user_course_ids = []
    
    if current_user.role == "student":
        # Get groups where user is a student
        user_groups = db.query(GroupStudent).filter(GroupStudent.student_id == current_user.id).all()
        user_group_ids = [ug.group_id for ug in user_groups]
        
        # Get courses where user is enrolled
        enrollments = db.query(Enrollment).filter(
            Enrollment.user_id == current_user.id,
            Enrollment.is_active == True
        ).all()
        user_course_ids = [e.course_id for e in enrollments]
        
        # Get courses accessible via user's groups
        if user_group_ids:
            from src.schemas.models import CourseGroupAccess
            group_access = db.query(CourseGroupAccess).filter(
                CourseGroupAccess.group_id.in_(user_group_ids),
                CourseGroupAccess.is_active == True
            ).all()
            group_course_ids = [ga.course_id for ga in group_access]
            user_course_ids.extend(group_course_ids)
            # Deduplicate
            user_course_ids = list(set(user_course_ids))
        
        # Get courses accessible via user's groups
        if user_group_ids:
            from src.schemas.models import CourseGroupAccess
            group_access = db.query(CourseGroupAccess).filter(
                CourseGroupAccess.group_id.in_(user_group_ids),
                CourseGroupAccess.is_active == True
            ).all()
            group_course_ids = [ga.course_id for ga in group_access]
            user_course_ids.extend(group_course_ids)
            # Deduplicate
            user_course_ids = list(set(user_course_ids))
        
    elif current_user.role in ["teacher", "curator"]:
        # Get groups where user is teacher or curator
        teacher_groups = db.query(Group).filter(Group.teacher_id == current_user.id).all()
        curator_groups = db.query(Group).filter(Group.curator_id == current_user.id).all()
        user_group_ids = [g.id for g in teacher_groups + curator_groups]
        
        # Teachers/Curators see events for courses they teach? 
        # For now, let's assume they see events for groups they manage.
        # If we want them to see course events, we'd need to know which courses they teach.
        # Assuming they see all events for now if they are admin, but here restricted.
        pass
        
    elif current_user.role == "admin":
        # Admins see all events
        user_group_ids = [g.id for g in db.query(Group).all()]
        user_course_ids = [c.id for c in db.query(Course).all()]
    
    if not user_group_ids and not user_course_ids:
        return []
    
    # Build query
    # Events that are in user's groups OR in user's courses
    
    query = db.query(Event).outerjoin(EventGroup).outerjoin(EventCourse).filter(
        or_(
            EventGroup.group_id.in_(user_group_ids),
            EventCourse.course_id.in_(user_course_ids)
        ),
        Event.is_active == True
    ).distinct()
    
    # Apply filters
    if event_type:
        query = query.filter(Event.event_type == event_type)
    if start_date:
        query = query.filter(Event.start_datetime >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(Event.start_datetime <= datetime.combine(end_date, datetime.max.time()))
    if upcoming_only:
        query = query.filter(Event.start_datetime >= datetime.utcnow())
    
    # Eager load relationships
    query = query.options(
        joinedload(Event.creator),
        joinedload(Event.event_groups).joinedload(EventGroup.group),
        joinedload(Event.event_courses).joinedload(EventCourse.course),
        joinedload(Event.lesson)
    )
    
    events = query.order_by(Event.start_datetime).offset(skip).limit(limit).all()
    
    # Batch fetch participant counts
    event_ids = [e.id for e in events]
    count_map = {}
    if event_ids:
        participant_counts = db.query(
            EventParticipant.event_id, 
            func.count(EventParticipant.id)
        ).filter(
            EventParticipant.event_id.in_(event_ids)
        ).group_by(EventParticipant.event_id).all()
        count_map = {event_id: count for event_id, count in participant_counts}
    
    # Enrich with additional data
    result = []
    for event in events:
        event_data = EventSchema.from_orm(event)
        event_data.creator_name = event.creator.name if event.creator else "Unknown"
        event_data.groups = [eg.group.name for eg in event.event_groups if eg.group]
        event_data.participant_count = count_map.get(event.id, 0)
        result.append(event_data)
        
    # Add Lesson Schedules
    if user_group_ids and (not event_type or event_type == "class"):
        ls_query = db.query(LessonSchedule).filter(
            LessonSchedule.group_id.in_(user_group_ids),
            LessonSchedule.is_active == True
        )
        if start_date:
            ls_query = ls_query.filter(LessonSchedule.scheduled_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            ls_query = ls_query.filter(LessonSchedule.scheduled_at <= datetime.combine(end_date, datetime.max.time()))
        if upcoming_only:
            ls_query = ls_query.filter(LessonSchedule.scheduled_at >= datetime.utcnow())
            
        lessons_schedules = ls_query.options(
            joinedload(LessonSchedule.lesson),
            joinedload(LessonSchedule.group)
        ).order_by(LessonSchedule.scheduled_at).offset(skip).limit(limit).all()
        
        for sched in lessons_schedules:
            lesson_event_id = 2000000000 + sched.id
            end_dt = sched.scheduled_at + timedelta(minutes=90)
            
            lesson_event = EventSchema(
                id=lesson_event_id,
                title=f"{sched.group.name}: {sched.lesson.title}",
                description=f"Lesson {sched.lesson.title} for group {sched.group.name}",
                event_type="class",
                start_datetime=sched.scheduled_at,
                end_datetime=end_dt,
                location="Online" if sched.group.name.startswith("Online") else "In Person",
                is_online=True,
                created_by=0,
                creator_name="System",
                is_active=True,
                is_recurring=False,
                participant_count=0,
                created_at=sched.scheduled_at,
                updated_at=sched.scheduled_at,
                groups=[sched.group.name],
                lesson_id=sched.lesson_id,
                group_ids=[sched.group_id]
            )
            result.append(lesson_event)
            
    # Sort and limit result if mixed
    result.sort(key=lambda x: x.start_datetime)
    return result[:limit]

@router.get("/calendar", response_model=List[EventSchema])
async def get_calendar_events(
    year: int = Query(..., ge=2020, le=2030),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Get events for calendar view by month"""
    
    # Calculate month boundaries
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)
    
    # Get user's groups and courses
    user_group_ids = []
    user_course_ids = []
    
    if current_user.role == "student":
        user_groups = db.query(GroupStudent).filter(GroupStudent.student_id == current_user.id).all()
        user_group_ids = [ug.group_id for ug in user_groups]
        
        enrollments = db.query(Enrollment).filter(
            Enrollment.user_id == current_user.id,
            Enrollment.is_active == True
        ).all()
        user_course_ids = [e.course_id for e in enrollments]
        
        # Get courses accessible via user's groups
        if user_group_ids:
            from src.schemas.models import CourseGroupAccess
            group_access = db.query(CourseGroupAccess).filter(
                CourseGroupAccess.group_id.in_(user_group_ids),
                CourseGroupAccess.is_active == True
            ).all()
            group_course_ids = [ga.course_id for ga in group_access]
            user_course_ids.extend(group_course_ids)
            # Deduplicate
            user_course_ids = list(set(user_course_ids))
        
        # Get courses accessible via user's groups
        if user_group_ids:
            from src.schemas.models import CourseGroupAccess
            group_access = db.query(CourseGroupAccess).filter(
                CourseGroupAccess.group_id.in_(user_group_ids),
                CourseGroupAccess.is_active == True
            ).all()
            group_course_ids = [ga.course_id for ga in group_access]
            user_course_ids.extend(group_course_ids)
            # Deduplicate
            user_course_ids = list(set(user_course_ids))
        
    elif current_user.role in ["teacher", "curator"]:
        teacher_groups = db.query(Group).filter(Group.teacher_id == current_user.id).all()
        curator_groups = db.query(Group).filter(Group.curator_id == current_user.id).all()
        user_group_ids = [g.id for g in teacher_groups + curator_groups]
        
    elif current_user.role == "admin":
        user_group_ids = [g.id for g in db.query(Group).all()]
        user_course_ids = [c.id for c in db.query(Course).all()]
    
    if not user_group_ids and not user_course_ids:
        print(f"DEBUG: No groups or courses for user {current_user.id}")
        return []
    
    import sys
    
    print(f"DEBUG: Calendar request - User: {current_user.id}, Role: {current_user.role}")
    print(f"DEBUG: Groups: {user_group_ids}")
    print(f"DEBUG: Courses: {user_course_ids}")
    print(f"DEBUG: Date Range: {start_date} to {end_date}")
    sys.stdout.flush()

    # Get events for the month with eager loading
    # 1. Get standard events in range
    
    standard_events = db.query(Event).outerjoin(EventGroup).outerjoin(EventCourse).filter(
        or_(
            EventGroup.group_id.in_(user_group_ids),
            EventCourse.course_id.in_(user_course_ids)
        ),
        Event.is_active == True,
        Event.start_datetime >= start_date,
        Event.start_datetime <= end_date,
        Event.is_recurring == False # Only non-recurring instances
    ).distinct().options(
        joinedload(Event.creator),
        joinedload(Event.event_groups).joinedload(EventGroup.group),
        joinedload(Event.event_courses).joinedload(EventCourse.course)
    ).all()

    # 2. Get recurring parent events that might overlap
    recurring_parents = db.query(Event).outerjoin(EventGroup).outerjoin(EventCourse).filter(
        or_(
            EventGroup.group_id.in_(user_group_ids),
            EventCourse.course_id.in_(user_course_ids)
        ),
        Event.is_active == True,
        Event.is_recurring == True,
        Event.start_datetime <= end_date,
        or_(
            Event.recurrence_end_date == None,
            Event.recurrence_end_date >= start_date.date()
        )
    ).distinct().options(
        joinedload(Event.creator),
        joinedload(Event.event_groups).joinedload(EventGroup.group),
        joinedload(Event.event_courses).joinedload(EventCourse.course)
    ).all()

    generated_events = []
    import calendar as cal_module

    for parent in recurring_parents:
        # Generate instances for this parent within [start_date, end_date]
        
        # Determine the effective start for generation
        # We need to find the first occurrence >= start_date
        
        current_start = parent.start_datetime
        current_end = parent.end_datetime
        duration = current_end - current_start
        
        # Optimization: Fast forward to near start_date if possible
        # This is complex for monthly, but easy for daily/weekly/biweekly
        
        # Simple iteration for now (robust but potentially slow if start_date is far in future)
        # TODO: Optimize fast-forwarding
        
        original_start_day = parent.start_datetime.day
        
        while current_start <= end_date:
            # Check if current instance is within range
            if current_start >= start_date and current_start <= end_date:
                # Create a virtual event copy
                # We use a special ID format or just negative IDs to distinguish?
                # For frontend, unique IDs are needed. 
                # Let's use string IDs in frontend? No, types say number.
                # We'll use a deterministic hash or large number offset?
                # Or just let them be 0/negative and handle in frontend?
                # Frontend expects 'id' to be number.
                
                # Let's generate a pseudo-ID based on parent ID and timestamp
                # This is a bit hacky but works for display
                pseudo_id = int(f"{parent.id}{int(current_start.timestamp())}") % 2147483647
                
                virtual_event = Event(
                    id=pseudo_id, # Virtual ID
                    title=parent.title,
                    description=parent.description,
                    event_type=parent.event_type,
                    start_datetime=current_start,
                    end_datetime=current_start + duration,
                    location=parent.location,
                    is_online=parent.is_online,
                    meeting_url=parent.meeting_url,
                    created_by=parent.created_by,
                    is_recurring=True, # It is part of a recurring series
                    recurrence_pattern=parent.recurrence_pattern,
                    max_participants=parent.max_participants,
                    creator=parent.creator,
                    event_groups=parent.event_groups,
                    created_at=parent.created_at,
                    updated_at=parent.updated_at,
                    is_active=True
                )
                generated_events.append(virtual_event)
            
            # Increment
            if parent.recurrence_pattern == "daily":
                current_start += timedelta(days=1)
            elif parent.recurrence_pattern == "weekly":
                current_start += timedelta(weeks=1)
            elif parent.recurrence_pattern == "biweekly":
                current_start += timedelta(weeks=2)
            elif parent.recurrence_pattern == "monthly":
                year = current_start.year + (current_start.month // 12)
                month = (current_start.month % 12) + 1
                day = min(original_start_day, cal_module.monthrange(year, month)[1])
                current_start = current_start.replace(year=year, month=month, day=day)
            else:
                break # Unknown pattern
            
            # Check if we passed the recurrence end date (if it exists)
            if parent.recurrence_end_date and current_start.date() > parent.recurrence_end_date:
                break

    # Combine and sort
    all_events = standard_events + generated_events
    all_events.sort(key=lambda x: x.start_datetime)
    

    # Batch fetch participant counts (only for real events)
    real_event_ids = [e.id for e in standard_events]
    count_map = {}
    
    if real_event_ids:
        participant_counts = db.query(
            EventParticipant.event_id, 
            func.count(EventParticipant.id)
        ).filter(
            EventParticipant.event_id.in_(real_event_ids)
        ).group_by(EventParticipant.event_id).all()
        
        count_map = {event_id: count for event_id, count in participant_counts}
    
    # Enrich with additional data
    result = []
    for event in all_events:
        # For virtual events, we might need to handle schema conversion manually 
        # because they are not attached to session
        
        event_data = EventSchema.from_orm(event)
        
        # Add creator name
        event_data.creator_name = event.creator.name if event.creator else "Unknown"
        
        # Add group names
        event_data.groups = [eg.group.name for eg in event.event_groups if eg.group]
        
        # Add participant count
        # For virtual events, we assume 0 or fetch from parent? 
        # Participants are usually per-instance. Virtual instances have no participants yet.
        event_data.participant_count = count_map.get(event.id, 0)
        
        result.append(event_data)
    
    # 3. Get Assignments as Events
    # Use split queries to ensure robustness and easy debugging
    
    found_assignments = []
    
    # 3a. Fetch by Group
    if user_group_ids:
        group_assignments = db.query(Assignment).filter(
            Assignment.is_active == True,
            Assignment.due_date >= start_date,
            Assignment.due_date <= end_date,
            or_(Assignment.is_hidden == False, Assignment.is_hidden == None),
            Assignment.group_id.in_(user_group_ids)
        ).all()
        found_assignments.extend(group_assignments)
        print(f"DEBUG: Found {len(group_assignments)} assignments via Group ID")
        
    # 3b. Fetch by Course -> Lesson
    # First get lesson IDs for user's courses to avoid subquery issues
    course_lesson_ids = []
    if user_course_ids:
        lesson_rows = db.query(Lesson.id).join(Module).filter(
            Module.course_id.in_(user_course_ids)
        ).all()
        course_lesson_ids = [r[0] for r in lesson_rows]
        
    if course_lesson_ids:
        lesson_assignments = db.query(Assignment).filter(
            Assignment.is_active == True,
            Assignment.due_date >= start_date,
            Assignment.due_date <= end_date,
            or_(Assignment.is_hidden == False, Assignment.is_hidden == None),
            Assignment.lesson_id.in_(course_lesson_ids)
        ).all()
        found_assignments.extend(lesson_assignments)
        
    # Deduplicate assignments by ID
    assignments = list({a.id: a for a in found_assignments}.values())
    
    if not assignments and user_group_ids:
        # Extra debug: check raw count of assignments for this group globally
        raw_count = db.query(Assignment).filter(Assignment.group_id.in_(user_group_ids)).count()
        
    sys.stdout.flush()
    
    # Convert assignments to Event schema
    for assignment in assignments:
        # Create a virtual event for the assignment deadline
        # ID logic: maybe use negative ID to avoid collision or string ID?
        # But schema requires integer ID.
        # We can offset ID by a large number, e.g. 1000000000 + assignment.id
        
        assign_event_id = 1000000000 + assignment.id
        
        # Determine duration (e.g. 1 hour ending at due_date)
        end_dt = assignment.due_date
        start_dt = end_dt - timedelta(hours=1)
        
        assign_event = EventSchema(
            id=assign_event_id,
            title=f"Deadline: {assignment.title}",
            description=assignment.description,
            event_type="assignment", # Custom type for frontend
            start_datetime=start_dt,
            end_datetime=end_dt,
            location="LMS",
            is_online=True,
            created_by=0, # System
            creator_name="System",
            is_active=True,
            is_recurring=False,
            participant_count=0,
            created_at=assignment.created_at,
            updated_at=assignment.created_at,
            groups=[], # We could fetch, but might be slow
            courses=[]
        )
        
        result.append(assign_event)
        
    # 4. Get Lesson Schedules as Events
    if user_group_ids:
        lessons_schedules = db.query(LessonSchedule).filter(
            LessonSchedule.group_id.in_(user_group_ids),
            LessonSchedule.is_active == True,
            LessonSchedule.scheduled_at >= start_date,
            LessonSchedule.scheduled_at <= end_date
        ).options(
            joinedload(LessonSchedule.lesson),
            joinedload(LessonSchedule.group)
        ).all()
        
        for sched in lessons_schedules:
            # Create a virtual event for the lesson
            # ID logic: offset by 2000000000 + sched.id
            lesson_event_id = 2000000000 + sched.id
            
            # End time default + 90 mins
            end_dt = sched.scheduled_at + timedelta(minutes=90)
            
            lesson_event = EventSchema(
                id=lesson_event_id,
                title=f"{sched.group.name}: {sched.lesson.title}",
                description=f"Lesson {sched.lesson.title} for group {sched.group.name}",
                event_type="class",
                start_datetime=sched.scheduled_at,
                end_datetime=end_dt,
                location="Online" if sched.group.name.startswith("Online") else "In Person",
                is_online=True, # Assuming online for now or checking group name
                created_by=0, # System
                creator_name="System",
                is_active=True,
                is_recurring=False,
                participant_count=0,
                created_at=sched.scheduled_at, # Fallback
                updated_at=sched.scheduled_at, # Fallback
                groups=[sched.group.name],
                lesson_id=sched.lesson_id,
                group_ids=[sched.group_id]
            )
            result.append(lesson_event)

    # Sort again by start date
    result.sort(key=lambda x: x.start_datetime)
    
    return result

@router.get("/upcoming", response_model=List[EventSchema])
async def get_upcoming_events(
    limit: int = Query(10, le=50),
    days_ahead: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Get upcoming events for current user"""
    
    # Calculate date range
    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=days_ahead)
    
    # Get user's groups and courses
    user_group_ids = []
    user_course_ids = []
    
    if current_user.role == "student":
        user_groups = db.query(GroupStudent).filter(GroupStudent.student_id == current_user.id).all()
        user_group_ids = [ug.group_id for ug in user_groups]
        
        enrollments = db.query(Enrollment).filter(
            Enrollment.user_id == current_user.id,
            Enrollment.is_active == True
        ).all()
        user_course_ids = [e.course_id for e in enrollments]
        
        # Get courses accessible via user's groups
        if user_group_ids:
            from src.schemas.models import CourseGroupAccess
            group_access = db.query(CourseGroupAccess).filter(
                CourseGroupAccess.group_id.in_(user_group_ids),
                CourseGroupAccess.is_active == True
            ).all()
            group_course_ids = [ga.course_id for ga in group_access]
            user_course_ids.extend(group_course_ids)
            # Deduplicate
            user_course_ids = list(set(user_course_ids))
        
        # Get courses accessible via user's groups
        if user_group_ids:
            from src.schemas.models import CourseGroupAccess
            group_access = db.query(CourseGroupAccess).filter(
                CourseGroupAccess.group_id.in_(user_group_ids),
                CourseGroupAccess.is_active == True
            ).all()
            group_course_ids = [ga.course_id for ga in group_access]
            user_course_ids.extend(group_course_ids)
            # Deduplicate
            user_course_ids = list(set(user_course_ids))
        
    elif current_user.role in ["teacher", "curator"]:
        teacher_groups = db.query(Group).filter(Group.teacher_id == current_user.id).all()
        curator_groups = db.query(Group).filter(Group.curator_id == current_user.id).all()
        user_group_ids = [g.id for g in teacher_groups + curator_groups]
        
    elif current_user.role == "admin":
        user_group_ids = [g.id for g in db.query(Group).all()]
        user_course_ids = [c.id for c in db.query(Course).all()]
    
    if not user_group_ids and not user_course_ids:
        return []
    
    # Get upcoming events with eager loading
    
    events = db.query(Event).outerjoin(EventGroup).outerjoin(EventCourse).filter(
        or_(
            EventGroup.group_id.in_(user_group_ids),
            EventCourse.course_id.in_(user_course_ids)
        ),
        Event.is_active == True,
        Event.start_datetime >= start_date,
        Event.start_datetime <= end_date
    ).distinct().options(
        joinedload(Event.creator),
        joinedload(Event.event_groups).joinedload(EventGroup.group),
        joinedload(Event.event_courses).joinedload(EventCourse.course)
    ).order_by(Event.start_datetime).limit(limit).all()
    
    # Batch fetch participant counts
    event_ids = [e.id for e in events]
    count_map = {}
    if event_ids:
        participant_counts = db.query(
            EventParticipant.event_id, 
            func.count(EventParticipant.id)
        ).filter(
            EventParticipant.event_id.in_(event_ids)
        ).group_by(EventParticipant.event_id).all()
        count_map = {event_id: count for event_id, count in participant_counts}
    
    # Enrich with additional data
    result = []
    for event in events:
        event_data = EventSchema.from_orm(event)
        event_data.creator_name = event.creator.name if event.creator else "Unknown"
        event_data.groups = [eg.group.name for eg in event.event_groups if eg.group]
        event_data.participant_count = count_map.get(event.id, 0)
        result.append(event_data)
        
    # Add upcoming Lesson Schedules
    if user_group_ids:
        ls_query = db.query(LessonSchedule).filter(
            LessonSchedule.group_id.in_(user_group_ids),
            LessonSchedule.is_active == True,
            LessonSchedule.scheduled_at >= start_date,
            LessonSchedule.scheduled_at <= end_date
        ).options(
            joinedload(LessonSchedule.lesson),
            joinedload(LessonSchedule.group)
        ).order_by(LessonSchedule.scheduled_at).limit(limit).all()
        
        for sched in ls_query:
            lesson_event_id = 2000000000 + sched.id
            end_dt = sched.scheduled_at + timedelta(minutes=90)
            
            lesson_event = EventSchema(
                id=lesson_event_id,
                title=f"{sched.group.name}: {sched.lesson.title}",
                description=f"Lesson {sched.lesson.title} for group {sched.group.name}",
                event_type="class",
                start_datetime=sched.scheduled_at,
                end_datetime=end_dt,
                location="Online" if sched.group.name.startswith("Online") else "In Person",
                is_online=True,
                created_by=0,
                creator_name="System",
                is_active=True,
                is_recurring=False,
                participant_count=0,
                created_at=sched.scheduled_at,
                updated_at=sched.scheduled_at,
                groups=[sched.group.name],
                lesson_id=sched.lesson_id,
                group_ids=[sched.group_id]
            )
            result.append(lesson_event)
            
    # Sort and limit
    result.sort(key=lambda x: x.start_datetime)
    return result[:limit]

@router.get("/{event_id}", response_model=EventSchema)
async def get_event_details(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Get detailed information about a specific event"""
    
    event = db.query(Event).filter(Event.id == event_id, Event.is_active == True).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Check if user has access to this event
    if current_user.role == "admin":
        # Admins have full access
        pass
    else:
        user_group_ids = []
        user_course_ids = []
        
        if current_user.role == "student":
            user_groups = db.query(GroupStudent).filter(GroupStudent.student_id == current_user.id).all()
            user_group_ids = [ug.group_id for ug in user_groups]
            
            enrollments = db.query(Enrollment).filter(
                Enrollment.user_id == current_user.id,
                Enrollment.is_active == True
            ).all()
            user_course_ids = [e.course_id for e in enrollments]
            
        elif current_user.role in ["teacher", "curator"]:
            teacher_groups = db.query(Group).filter(Group.teacher_id == current_user.id).all()
            curator_groups = db.query(Group).filter(Group.curator_id == current_user.id).all()
            user_group_ids = [g.id for g in teacher_groups + curator_groups]
            
            # For teachers/curators, we might want to check courses they teach
            # For now, assuming if they are not admin, they are restricted to their groups
            # If we want to support course teachers seeing events:
            courses_taught = db.query(Course).filter(Course.teacher_id == current_user.id).all()
            user_course_ids = [c.id for c in courses_taught]
        
        # Check if event is associated with user's groups or courses
        
        event_groups = db.query(EventGroup).filter(EventGroup.event_id == event_id).all()
        event_group_ids = [eg.group_id for eg in event_groups]
        
        event_courses = db.query(EventCourse).filter(EventCourse.event_id == event_id).all()
        event_course_ids = [ec.course_id for ec in event_courses]
        
        has_group_access = any(group_id in user_group_ids for group_id in event_group_ids)
        has_course_access = any(course_id in user_course_ids for course_id in event_course_ids)
        
        if not (has_group_access or has_course_access):
            raise HTTPException(status_code=403, detail="Access denied to this event")
    
    # Enrich event data
    event_data = EventSchema.from_orm(event)
    
    # Add creator name
    creator = db.query(UserInDB).filter(UserInDB.id == event.created_by).first()
    event_data.creator_name = creator.name if creator else "Unknown"

    # Add teacher name
    if event.teacher_id:
        teacher = db.query(UserInDB).filter(UserInDB.id == event.teacher_id).first()
        event_data.teacher_name = teacher.name if teacher else None
    
    # Add group names
    event_data.groups = [eg.group.name for eg in event.event_groups if eg.group]
    
    # Add course names
    event_data.courses = [ec.course.title for ec in event.event_courses if ec.course]
    
    # Add group IDs
    event_data.group_ids = [eg.group_id for eg in event.event_groups]
    
    # Add course IDs
    event_data.course_ids = [ec.course_id for ec in event.event_courses]
    
    # Add participant count
    participant_count = db.query(EventParticipant).filter(EventParticipant.event_id == event.id).count()
    event_data.participant_count = participant_count
    
    return event_data

@router.post("/{event_id}/register")
async def register_for_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Register current user for an event (for webinars mainly)"""
    
    event = db.query(Event).filter(Event.id == event_id, Event.is_active == True).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Check if user has access to this event
    user_group_ids = []
    if current_user.role == "student":
        user_groups = db.query(GroupStudent).filter(GroupStudent.student_id == current_user.id).all()
        user_group_ids = [ug.group_id for ug in user_groups]
    elif current_user.role in ["teacher", "curator"]:
        teacher_groups = db.query(Group).filter(Group.teacher_id == current_user.id).all()
        curator_groups = db.query(Group).filter(Group.curator_id == current_user.id).all()
        user_group_ids = [g.id for g in teacher_groups + curator_groups]
    elif current_user.role == "admin":
        user_group_ids = [g.id for g in db.query(Group).all()]
    
    event_groups = db.query(EventGroup).filter(EventGroup.event_id == event_id).all()
    event_group_ids = [eg.group_id for eg in event_groups]
    
    if not any(group_id in user_group_ids for group_id in event_group_ids):
        raise HTTPException(status_code=403, detail="Access denied to this event")
    
    # Check if already registered
    existing_registration = db.query(EventParticipant).filter(
        EventParticipant.event_id == event_id,
        EventParticipant.user_id == current_user.id
    ).first()
    
    if existing_registration:
        raise HTTPException(status_code=400, detail="Already registered for this event")
    
    # Check max participants limit
    if event.max_participants:
        current_participants = db.query(EventParticipant).filter(EventParticipant.event_id == event_id).count()
        if current_participants >= event.max_participants:
            raise HTTPException(status_code=400, detail="Event is full")
    
    # Create registration
    registration = EventParticipant(
        event_id=event_id,
        user_id=current_user.id,
        registration_status="registered"
    )
    
    db.add(registration)
    db.commit()
    
    return {"detail": "Successfully registered for event"}

@router.delete("/{event_id}/register")
async def unregister_from_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Unregister current user from an event"""
    
    registration = db.query(EventParticipant).filter(
        EventParticipant.event_id == event_id,
        EventParticipant.user_id == current_user.id
    ).first()
    
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
    
    db.delete(registration)
    db.commit()
    
    return {"detail": "Successfully unregistered from event"}

@router.post("/curator/create", response_model=EventSchema)
async def create_curator_event(
    event_data: CreateEventRequest,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Create a new event as curator for managed groups"""
    
    # Only curators and admins can create events
    if current_user.role not in ["curator", "admin", "head_curator"]:
        raise HTTPException(status_code=403, detail="Only curators and admins can create events")
    
    # Validate event type
    valid_types = ["class", "weekly_test", "webinar"]
    if event_data.event_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid event type. Must be one of: {valid_types}")
    
    # Validate datetime
    if event_data.start_datetime >= event_data.end_datetime:
        raise HTTPException(status_code=400, detail="Start datetime must be before end datetime")
    
    # For curators: verify they manage all specified groups
    if current_user.role == "curator" and event_data.group_ids:
        curator_groups = db.query(Group).filter(
            Group.curator_id == current_user.id,
            Group.id.in_(event_data.group_ids)
        ).all()
        
        if len(curator_groups) != len(event_data.group_ids):
            raise HTTPException(
                status_code=403, 
                detail="You can only create events for groups you manage"
            )
    
    # Validate groups exist
    groups = []
    if event_data.group_ids:
        groups = db.query(Group).filter(Group.id.in_(event_data.group_ids)).all()
        if len(groups) != len(event_data.group_ids):
            raise HTTPException(status_code=400, detail="One or more groups not found")

    # Validate courses exist (optional)
    courses = []
    if event_data.course_ids:
        courses = db.query(Course).filter(Course.id.in_(event_data.course_ids)).all()
        if len(courses) != len(event_data.course_ids):
            raise HTTPException(status_code=400, detail="One or more courses not found")
    
    # Create event
    event = Event(
        title=event_data.title,
        description=event_data.description,
        event_type=event_data.event_type,
        start_datetime=event_data.start_datetime,
        end_datetime=event_data.end_datetime,
        location=event_data.location,
        is_online=event_data.is_online,
        meeting_url=event_data.meeting_url,
        created_by=current_user.id,
        is_recurring=event_data.is_recurring,
        recurrence_pattern=event_data.recurrence_pattern,
        recurrence_end_date=event_data.recurrence_end_date,
        max_participants=event_data.max_participants,
        lesson_id=event_data.lesson_id,
        teacher_id=event_data.teacher_id
    )
    
    db.add(event)
    db.flush()  # To get the event ID
    
    # Create event-group associations
    for group_id in event_data.group_ids:
        event_group = EventGroup(event_id=event.id, group_id=group_id)
        db.add(event_group)

    # Create event-course associations
    if event_data.course_ids:
        for course_id in event_data.course_ids:
            event_course = EventCourse(event_id=event.id, course_id=course_id)
            db.add(event_course)
    
    db.commit()
    db.refresh(event)
    
    # Return enriched event data
    result = EventSchema.from_orm(event)
    result.creator_name = current_user.name
    result.groups = [g.name for g in groups] if event_data.group_ids else []
    result.group_ids = event_data.group_ids or []
    result.course_ids = event_data.course_ids or []
    
    if event_data.course_ids:
        course_names = [c.title for c in courses]
        result.courses = course_names
    else:
        result.courses = []
    
    return result
