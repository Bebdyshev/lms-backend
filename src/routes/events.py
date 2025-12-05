from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, and_, or_
from typing import List, Optional
from datetime import datetime, date, timedelta

from src.config import get_db
from src.schemas.models import (
    UserInDB, Event, EventGroup, EventParticipant, Group, GroupStudent,
    EventSchema, EventParticipantSchema
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
    
    # Get user's groups
    user_group_ids = []
    if current_user.role == "student":
        # Get groups where user is a student
        user_groups = db.query(GroupStudent).filter(GroupStudent.student_id == current_user.id).all()
        user_group_ids = [ug.group_id for ug in user_groups]
    elif current_user.role in ["teacher", "curator"]:
        # Get groups where user is teacher or curator
        teacher_groups = db.query(Group).filter(Group.teacher_id == current_user.id).all()
        curator_groups = db.query(Group).filter(Group.curator_id == current_user.id).all()
        user_group_ids = [g.id for g in teacher_groups + curator_groups]
    elif current_user.role == "admin":
        # Admins see all events
        user_group_ids = [g.id for g in db.query(Group).all()]
    
    if not user_group_ids:
        return []
    
    # Build query
    query = db.query(Event).join(EventGroup).filter(
        EventGroup.group_id.in_(user_group_ids),
        Event.is_active == True
    )
    
    # Apply filters
    if event_type:
        query = query.filter(Event.event_type == event_type)
    if start_date:
        query = query.filter(Event.start_datetime >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(Event.end_datetime <= datetime.combine(end_date, datetime.max.time()))
    if upcoming_only:
        query = query.filter(Event.start_datetime >= datetime.utcnow())
    
    # Eager load relationships
    query = query.options(
        joinedload(Event.creator),
        joinedload(Event.event_groups).joinedload(EventGroup.group)
    )
    
    events = query.order_by(Event.start_datetime).offset(skip).limit(limit).all()
    
    if not events:
        return []

    # Batch fetch participant counts
    event_ids = [e.id for e in events]
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
        
        # Add creator name
        event_data.creator_name = event.creator.name if event.creator else "Unknown"
        
        # Add group names
        event_data.groups = [eg.group.name for eg in event.event_groups if eg.group]
        
        # Add participant count
        event_data.participant_count = count_map.get(event.id, 0)
        
        result.append(event_data)
    
    return result

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
    
    # Get user's groups
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
    
    if not user_group_ids:
        return []
    
    # Get events for the month with eager loading
    # 1. Get standard events in range
    standard_events = db.query(Event).join(EventGroup).filter(
        EventGroup.group_id.in_(user_group_ids),
        Event.is_active == True,
        Event.start_datetime >= start_date,
        Event.start_datetime <= end_date,
        Event.is_recurring == False # Only non-recurring instances
    ).options(
        joinedload(Event.creator),
        joinedload(Event.event_groups).joinedload(EventGroup.group)
    ).all()

    # 2. Get recurring parent events that might overlap
    # We look for events that started before the end of our range
    # and either have no end date OR have an end date after the start of our range
    recurring_parents = db.query(Event).join(EventGroup).filter(
        EventGroup.group_id.in_(user_group_ids),
        Event.is_active == True,
        Event.is_recurring == True,
        Event.start_datetime <= end_date,
        or_(
            Event.recurrence_end_date == None,
            Event.recurrence_end_date >= start_date.date()
        )
    ).options(
        joinedload(Event.creator),
        joinedload(Event.event_groups).joinedload(EventGroup.group)
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
    
    if not all_events:
        return []

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
    
    # Get user's groups
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
    
    if not user_group_ids:
        return []
    
    # Get upcoming events with eager loading
    events = db.query(Event).join(EventGroup).filter(
        EventGroup.group_id.in_(user_group_ids),
        Event.is_active == True,
        Event.start_datetime >= start_date,
        Event.start_datetime <= end_date
    ).options(
        joinedload(Event.creator),
        joinedload(Event.event_groups).joinedload(EventGroup.group)
    ).order_by(Event.start_datetime).limit(limit).all()
    
    if not events:
        return []

    # Batch fetch participant counts
    event_ids = [e.id for e in events]
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
        
        # Add creator name
        event_data.creator_name = event.creator.name if event.creator else "Unknown"
        
        # Add group names
        event_data.groups = [eg.group.name for eg in event.event_groups if eg.group]
        
        # Add participant count
        event_data.participant_count = count_map.get(event.id, 0)
        
        result.append(event_data)
    
    return result

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
    
    # Check if event is associated with user's groups
    event_groups = db.query(EventGroup).filter(EventGroup.event_id == event_id).all()
    event_group_ids = [eg.group_id for eg in event_groups]
    
    if not any(group_id in user_group_ids for group_id in event_group_ids):
        raise HTTPException(status_code=403, detail="Access denied to this event")
    
    # Enrich event data
    event_data = EventSchema.from_orm(event)
    
    # Add creator name
    creator = db.query(UserInDB).filter(UserInDB.id == event.created_by).first()
    event_data.creator_name = creator.name if creator else "Unknown"
    
    # Add group names
    group_names = []
    for eg in event_groups:
        group = db.query(Group).filter(Group.id == eg.group_id).first()
        if group:
            group_names.append(group.name)
    event_data.groups = group_names
    
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
