"""
Lesson Substitution & Reschedule Request Routes
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import logging

from src.config import get_db
from src.schemas.models import (
    UserInDB, Group, LessonSchedule, Event, EventGroup,
    LessonRequest, LessonRequestSchema, CreateLessonRequestSchema, ResolveLessonRequestSchema,
    Notification, GroupStudent, Course, CourseGroupAccess,
)
from src.routes.auth import get_current_user_dependency
from src.utils.permissions import require_admin
from src.services.event_service import EventService

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# TEACHER ENDPOINTS
# =============================================================================

@router.post("/", response_model=LessonRequestSchema)
async def create_lesson_request(
    data: CreateLessonRequestSchema,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency),
):
    """Create a new lesson substitution or reschedule request (teacher only)."""
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Only teachers can create lesson requests")

    if data.request_type not in ("substitution", "reschedule"):
        raise HTTPException(status_code=400, detail="request_type must be 'substitution' or 'reschedule'")

    # Validate group
    group = db.query(Group).filter(Group.id == data.group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Resolve teacher IDs list (new list format or legacy single ID)
    teacher_ids = data.substitute_teacher_ids or ([data.substitute_teacher_id] if data.substitute_teacher_id else [])

    # For substitution – validate substitute teachers
    if data.request_type == "substitution":
        if not teacher_ids:
            raise HTTPException(status_code=400, detail="At least one substitute teacher is required for substitution")
        for tid in teacher_ids:
            sub_teacher = db.query(UserInDB).filter(
                UserInDB.id == tid,
                UserInDB.role == "teacher",
                UserInDB.is_active == True,
            ).first()
            if not sub_teacher:
                raise HTTPException(status_code=404, detail=f"Substitute teacher {tid} not found")
            if sub_teacher.no_substitutions:
                raise HTTPException(status_code=400, detail=f"Teacher {sub_teacher.name} has opted out of substitutions")

    # For reschedule – validate new datetime
    if data.request_type == "reschedule":
        if not data.new_datetime:
            raise HTTPException(status_code=400, detail="new_datetime required for reschedule")

    # Validation: Cannot create requests for past lessons
    original_dt = data.original_datetime
    if not original_dt.tzinfo:
        original_dt = original_dt.replace(tzinfo=timezone.utc)
        
    if original_dt < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="Cannot create requests for past lessons."
        )

    # Check monthly limit (2 per group)
    # Filter by current user, current group, status NOT rejected, and same month/year
    import calendar
    req_year = original_dt.year
    req_month = original_dt.month
    
    # Calculate month bounds
    _, last_day = calendar.monthrange(req_year, req_month)
    month_start = datetime(req_year, req_month, 1, 0, 0, 0, tzinfo=timezone.utc)
    month_end = datetime(req_year, req_month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    
    month_count = db.query(LessonRequest).filter(
        LessonRequest.requester_id == current_user.id,
        LessonRequest.group_id == data.group_id,
        LessonRequest.status.in_(["pending", "pending_teacher", "approved"]),
        LessonRequest.original_datetime >= month_start,
        LessonRequest.original_datetime <= month_end
    ).count()

    if month_count >= 2:
        raise HTTPException(
            status_code=400,
            detail="Monthly limit reached: You can only request 2 substitutions/reschedules per group per month."
        )

    # Check for existing pending request_type,
    import json
    new_request = LessonRequest(
        request_type=data.request_type,
        requester_id=current_user.id,
        lesson_schedule_id=data.lesson_schedule_id,
        event_id=data.event_id,
        group_id=data.group_id,
        original_datetime=data.original_datetime,
        substitute_teacher_id=teacher_ids[0] if teacher_ids else None,
        substitute_teacher_ids=json.dumps(teacher_ids) if teacher_ids else None,
        new_datetime=data.new_datetime,
        reason=data.reason,
        status="pending_teacher" if data.request_type == "substitution" else "pending",
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    # Notify admins
    _notify_admins_of_request(db, new_request, current_user)

    return _enrich_request(new_request, db)


@router.get("/me", response_model=List[LessonRequestSchema])
async def get_my_lesson_requests(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency),
):
    """Get lesson requests created by the current teacher."""
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Only teachers can view their requests")

    query = db.query(LessonRequest).filter(LessonRequest.requester_id == current_user.id)
    if status_filter:
        query = query.filter(LessonRequest.status == status_filter)

    requests = query.order_by(LessonRequest.created_at.desc()).all()
    return [_enrich_request(r, db) for r in requests]


@router.get("/incoming", response_model=List[LessonRequestSchema])
async def get_incoming_requests(
    history: bool = False,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency),
):
    """Get requests where current user is a candidate substitute."""
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can view incoming requests")

    # 1. Pending requests where user is a candidate
    all_pending = db.query(LessonRequest).filter(
        LessonRequest.status == "pending_teacher",
        LessonRequest.request_type == "substitution"
    ).all()

    results = []
    
    import json
    for req in all_pending:
        if req.substitute_teacher_ids:
            try:
                ids = json.loads(req.substitute_teacher_ids)
                if current_user.id in ids:
                    results.append(req)
            except:
                pass
                
    # 2. If history requested, include requests confirmed by this user
    if history:
        confirmed_by_me = db.query(LessonRequest).filter(
            LessonRequest.confirmed_teacher_id == current_user.id
        ).all()
        # Deduplicate if necessary (though state shouldn't overlap)
        existing_ids = {r.id for r in results}
        for r in confirmed_by_me:
            if r.id not in existing_ids:
                results.append(r)

    # Sort by created_at desc
    results.sort(key=lambda x: x.created_at, reverse=True)
    
    return [_enrich_request(r, db) for r in results]


@router.post("/{request_id}/confirm", response_model=LessonRequestSchema)
async def confirm_substitution_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency),
):
    """Substitute teacher confirms they can take the class."""
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can confirm requests")

    req = db.query(LessonRequest).filter(LessonRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if req.status != "pending_teacher":
        raise HTTPException(status_code=400, detail="Request is not pending teacher confirmation")

    # Verify user is in the candidate list
    import json
    candidate_ids = []
    if req.substitute_teacher_ids:
        try:
            candidate_ids = json.loads(req.substitute_teacher_ids)
        except:
            pass
    
    if current_user.id not in candidate_ids:
        raise HTTPException(status_code=403, detail="You are not a candidate for this request")

    # Update request
    req.status = "pending"  # Now ready for admin review
    req.confirmed_teacher_id = current_user.id
    req.substitute_teacher_id = current_user.id # Set as primary
    db.commit()
    db.refresh(req)

    # Notify admins that a teacher confirmed
    _notify_admins_of_confirmation(db, req, current_user)

    return _enrich_request(req, db)


@router.post("/{request_id}/decline", response_model=LessonRequestSchema)
async def decline_substitution_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency),
):
    """Substitute teacher declines the request."""
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can decline requests")

    req = db.query(LessonRequest).filter(LessonRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    # Verify user is in the candidate list
    import json
    candidate_ids = []
    if req.substitute_teacher_ids:
        try:
            candidate_ids = json.loads(req.substitute_teacher_ids)
        except:
            pass
    
    if current_user.id not in candidate_ids:
        raise HTTPException(status_code=403, detail="You are not a candidate for this request")

    # Remove user from candidate list
    new_ids = [uid for uid in candidate_ids if uid != current_user.id]
    req.substitute_teacher_ids = json.dumps(new_ids)

    # If no candidates left, maybe auto-reject or notify requester? 
    # For now, just leave it as is, or mark as rejected if empty.
    if not new_ids:
        req.status = "rejected"
        req.admin_comment = "All candidates declined."
        req.resolved_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(req)
    return _enrich_request(req, db)


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

@router.get("/", response_model=List[LessonRequestSchema])
async def list_lesson_requests(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(require_admin()),
):
    """List all lesson requests (admin only)."""
    query = db.query(LessonRequest)
    if status_filter:
        query = query.filter(LessonRequest.status == status_filter)

    requests = query.order_by(LessonRequest.created_at.desc()).all()
    return [_enrich_request(r, db) for r in requests]


@router.post("/{request_id}/approve", response_model=LessonRequestSchema)
async def approve_lesson_request(
    request_id: int,
    data: ResolveLessonRequestSchema,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(require_admin()),
):
    """Approve a lesson request – applies the substitution or reschedule."""
    lr = db.query(LessonRequest).filter(LessonRequest.id == request_id).first()
    if not lr:
        raise HTTPException(status_code=404, detail="Request not found")
    if lr.status != "pending":
        raise HTTPException(status_code=400, detail="Request already resolved")

    # Apply the change
    if lr.request_type == "substitution":
        _apply_substitution(db, lr, current_user.id)
    elif lr.request_type == "reschedule":
        _apply_reschedule(db, lr, current_user.id)

    lr.status = "approved"
    lr.admin_comment = data.admin_comment
    lr.resolved_at = datetime.now(timezone.utc)
    lr.resolved_by = current_user.id
    db.commit()
    db.refresh(lr)

    # Notify the requester and group students
    _notify_resolution(db, lr, approved=True)

    return _enrich_request(lr, db)


@router.post("/{request_id}/reject", response_model=LessonRequestSchema)
async def reject_lesson_request(
    request_id: int,
    data: ResolveLessonRequestSchema,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(require_admin()),
):
    """Reject a lesson request."""
    lr = db.query(LessonRequest).filter(LessonRequest.id == request_id).first()
    if not lr:
        raise HTTPException(status_code=404, detail="Request not found")
    if lr.status != "pending":
        raise HTTPException(status_code=400, detail="Request already resolved")

    lr.status = "rejected"
    lr.admin_comment = data.admin_comment
    lr.resolved_at = datetime.now(timezone.utc)
    lr.resolved_by = current_user.id
    db.commit()
    db.refresh(lr)

    # Notify requester
    _notify_resolution(db, lr, approved=False)

    return _enrich_request(lr, db)


# =============================================================================
# TEACHER AVAILABILITY SEARCH
# =============================================================================

@router.get("/teachers/available")
async def get_available_teachers(
    datetime_str: str = Query(..., description="ISO datetime for the lesson slot"),
    group_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency),
):
    """
    Find teachers available at a given time who have NOT opted out of substitutions.
    Excludes the requesting teacher and teachers who already have lessons at that time.
    """
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        target_dt = datetime.fromisoformat(datetime_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format, use ISO format")

    # Window: ±30 minutes from the target time
    window_start = target_dt - timedelta(minutes=30)
    window_end = target_dt + timedelta(minutes=90)

    # All active teachers who haven't opted out
    query = db.query(UserInDB).filter(
        UserInDB.role == "teacher",
        UserInDB.is_active == True,
        UserInDB.no_substitutions == False,
        UserInDB.id != current_user.id,
    )

    # Filter by Course Access if group_id is provided
    if group_id:
        # 1. Find courses accessed by this group
        course_ids = [c[0] for c in db.query(CourseGroupAccess.course_id).filter(
            CourseGroupAccess.group_id == group_id,
            CourseGroupAccess.is_active == True
        ).all()]

        if course_ids:
            # 2. Find all groups that access any of these courses
            relevant_group_ids = [g[0] for g in db.query(CourseGroupAccess.group_id).filter(
                CourseGroupAccess.course_id.in_(course_ids),
                CourseGroupAccess.is_active == True
            ).all()]

            # 3. Find teachers of these groups
            allowed_teacher_ids = set()
            if relevant_group_ids:
                group_teachers = db.query(Group.teacher_id).filter(Group.id.in_(relevant_group_ids)).all()
                for t in group_teachers:
                    allowed_teacher_ids.add(t[0])
            
            # 4. Also include teachers who created/manage the courses directly
            course_teachers = db.query(Course.teacher_id).filter(
                Course.id.in_(course_ids), 
                Course.teacher_id.isnot(None)
            ).all()
            for ct in course_teachers:
                allowed_teacher_ids.add(ct[0])
            
            # Apply filter
            if allowed_teacher_ids:
                query = query.filter(UserInDB.id.in_(allowed_teacher_ids))
            else:
                # If no teachers found for this course, return empty or fallback? 
                # Strict filtering: if course exists but no other teachers, returns empty.
                query = query.filter(UserInDB.id == -1) # specific to this implementation 

    teachers = query.all()

    # Find teachers busy in that window (have events at that time)
    busy_teacher_ids = set()

    # Check actual events
    busy_events = db.query(Event).filter(
        Event.is_active == True,
        Event.teacher_id.isnot(None),
        Event.start_datetime < window_end,
        Event.end_datetime > window_start,
    ).all()
    for ev in busy_events:
        busy_teacher_ids.add(ev.teacher_id)

    # Check lesson schedules
    busy_schedules = db.query(LessonSchedule).filter(
        LessonSchedule.is_active == True,
        LessonSchedule.scheduled_at >= window_start,
        LessonSchedule.scheduled_at < window_end,
    ).all()
    for sched in busy_schedules:
        if sched.group and sched.group.teacher_id:
            busy_teacher_ids.add(sched.group.teacher_id)

    available = []
    for t in teachers:
        if t.id not in busy_teacher_ids:
            available.append({
                "id": t.id,
                "name": t.name,
                "email": t.email,
            })

    return {"available_teachers": available}


# =============================================================================
# TEACHER PREFERENCE
# =============================================================================

@router.put("/preferences/no-substitutions")
async def update_substitution_preference(
    enabled: bool = Query(..., description="True to opt-out from substitutions"),
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_dependency),
):
    """Toggle the no_substitutions preference for the current teacher."""
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can change this preference")

    current_user.no_substitutions = enabled
    db.commit()
    return {"detail": "Preference updated", "no_substitutions": enabled}


# =============================================================================
# HELPERS
# =============================================================================

def _enrich_request(lr: LessonRequest, db: Session) -> LessonRequestSchema:
    """Convert a LessonRequest ORM object to LessonRequestSchema with names."""
    import json
    requester = db.query(UserInDB).filter(UserInDB.id == lr.requester_id).first()
    group = db.query(Group).filter(Group.id == lr.group_id).first()
    sub_teacher = None
    if lr.substitute_teacher_id:
        sub_teacher = db.query(UserInDB).filter(UserInDB.id == lr.substitute_teacher_id).first()

    confirmed_teacher = None
    if lr.confirmed_teacher_id:
        confirmed_teacher = db.query(UserInDB).filter(UserInDB.id == lr.confirmed_teacher_id).first()

    # Parse substitute_teacher_ids JSON
    teacher_ids_list = None
    teacher_names_list = None
    if lr.substitute_teacher_ids:
        try:
            teacher_ids_list = json.loads(lr.substitute_teacher_ids)
            teacher_names_list = []
            for tid in teacher_ids_list:
                t = db.query(UserInDB).filter(UserInDB.id == tid).first()
                teacher_names_list.append(t.name if t else "Unknown")
        except (json.JSONDecodeError, TypeError):
            pass

    return LessonRequestSchema(
        id=lr.id,
        request_type=lr.request_type,
        status=lr.status,
        requester_id=lr.requester_id,
        requester_name=requester.name if requester else None,
        lesson_schedule_id=lr.lesson_schedule_id,
        event_id=lr.event_id,
        group_id=lr.group_id,
        group_name=group.name if group else None,
        original_datetime=lr.original_datetime,
        substitute_teacher_id=lr.substitute_teacher_id,
        substitute_teacher_name=sub_teacher.name if sub_teacher else None,
        substitute_teacher_ids=teacher_ids_list,
        substitute_teacher_names=teacher_names_list,
        confirmed_teacher_id=lr.confirmed_teacher_id,
        confirmed_teacher_name=confirmed_teacher.name if confirmed_teacher else None,
        new_datetime=lr.new_datetime,
        reason=lr.reason,
        admin_comment=lr.admin_comment,
        created_at=lr.created_at,
        resolved_at=lr.resolved_at,
        resolved_by=lr.resolved_by,
    )


def _apply_substitution(db: Session, lr: LessonRequest, admin_id: int):
    """Materialize the event if needed and swap the teacher."""
    event_id = lr.event_id
    print(f"DEBUG_SUB: Applying sub/reschedule for req={lr.id} schedule={lr.lesson_schedule_id} event={event_id}")

    # If linked to a schedule but no event, materialize it
    if not event_id and lr.lesson_schedule_id:
        event_id = EventService.materialize_lesson_schedule(db, lr.lesson_schedule_id, user_id=admin_id)
        lr.event_id = event_id
        db.add(lr)  # Ensure session tracks the change

    if event_id:
        event = db.query(Event).filter(Event.id == event_id).first()
        if event:
            # Use confirmed teacher if available, fallback to old substitute_teacher_id
            new_teacher_id = lr.confirmed_teacher_id or lr.substitute_teacher_id
            if new_teacher_id:
                print(f"DEBUG_SUB: Setting event {event.id} teacher_id to {new_teacher_id}")
                event.teacher_id = new_teacher_id
                db.flush()


def _apply_reschedule(db: Session, lr: LessonRequest, admin_id: int):
    """Materialize the event if needed and change its datetime."""
    event_id = lr.event_id

    if not event_id and lr.lesson_schedule_id:
        event_id = EventService.materialize_lesson_schedule(db, lr.lesson_schedule_id, user_id=admin_id)
        lr.event_id = event_id
        db.add(lr)

    if event_id and lr.new_datetime:
        event = db.query(Event).filter(Event.id == event_id).first()
        if event:
            duration = event.end_datetime - event.start_datetime
            event.start_datetime = lr.new_datetime
            event.end_datetime = lr.new_datetime + duration
            db.flush()


def _notify_admins_of_request(db: Session, lr: LessonRequest, requester: UserInDB):
    """Create in-app notifications for admins about a new request."""
    admins = db.query(UserInDB).filter(UserInDB.role == "admin", UserInDB.is_active == True).all()
    group = db.query(Group).filter(Group.id == lr.group_id).first()
    group_name = group.name if group else "Unknown Group"

    for admin in admins:
        notification = Notification(
            user_id=admin.id,
            title="New Lesson Request",
            content=f"{requester.name} requested a {lr.request_type} for {group_name} on {lr.original_datetime.strftime('%d %b %Y %H:%M')}",
            notification_type="lesson_request",
            related_id=lr.id,
        )
        db.add(notification)
    db.commit()


def _notify_resolution(db: Session, lr: LessonRequest, approved: bool):
    """Notify the requester and group students about the resolution."""
    status_word = "approved" if approved else "rejected"
    group = db.query(Group).filter(Group.id == lr.group_id).first()
    group_name = group.name if group else "Unknown Group"

    # Notify the requesting teacher
    notification = Notification(
        user_id=lr.requester_id,
        title=f"Lesson Request {status_word.title()}",
        content=f"Your {lr.request_type} request for {group_name} has been {status_word}.",
        notification_type="lesson_request",
        related_id=lr.id,
    )
    db.add(notification)

    # If approved, notify students in the group
    if approved:
        student_ids = db.query(GroupStudent.student_id).filter(
            GroupStudent.group_id == lr.group_id
        ).all()

        if lr.request_type == "substitution":
            sub_teacher = db.query(UserInDB).filter(UserInDB.id == lr.substitute_teacher_id).first()
            sub_name = sub_teacher.name if sub_teacher else "another teacher"
            msg = f"Your class in {group_name} on {lr.original_datetime.strftime('%d %b %Y %H:%M')} will be taught by {sub_name}."
        else:
            new_dt = lr.new_datetime.strftime('%d %b %Y %H:%M') if lr.new_datetime else "TBD"
            msg = f"Your class in {group_name} has been rescheduled from {lr.original_datetime.strftime('%d %b %Y %H:%M')} to {new_dt}."

        for (sid,) in student_ids:
            notification = Notification(
                user_id=sid,
                title="Lesson Change",
                content=msg,
                notification_type="lesson_request",
                related_id=lr.id,
            )
            db.add(notification)

    db.commit()


def _notify_admins_of_confirmation(db: Session, lr: LessonRequest, teacher: UserInDB):
    """Notify admins that a substitute teacher has confirmed."""
    admins = db.query(UserInDB).filter(UserInDB.role == "admin", UserInDB.is_active == True).all()
    group = db.query(Group).filter(Group.id == lr.group_id).first()
    group_name = group.name if group else "Unknown Group"

    for admin in admins:
        notification = Notification(
            user_id=admin.id,
            title="Substitution Confirmed",
            content=f"{teacher.name} confirmed substitution for {group_name}. Ready for approval.",
            notification_type="lesson_request",
            related_id=lr.id,
        )
        db.add(notification)
    db.commit()
