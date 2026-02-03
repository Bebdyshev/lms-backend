#!/usr/bin/env python3
"""
Check events in the next 24 hours
"""
import logging
from datetime import datetime, timedelta
from src.config import SessionLocal
from src.schemas.models import Event, EventGroup, Group

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

db = SessionLocal()
try:
    now = datetime.utcnow()
    next_24h = now + timedelta(hours=24)
    
    logger.info("=" * 80)
    logger.info("EVENTS IN NEXT 24 HOURS")
    logger.info("=" * 80)
    logger.info(f"Current UTC time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Searching for events until: {next_24h.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    
    # Get events in next 24h
    events = db.query(Event).filter(
        Event.start_datetime > now,
        Event.start_datetime <= next_24h,
        Event.is_active == True
    ).order_by(Event.start_datetime).all()
    
    logger.info(f"Found {len(events)} active events")
    logger.info("")
    
    for i, event in enumerate(events, 1):
        # Get groups
        event_groups = db.query(EventGroup).filter(
            EventGroup.event_id == event.id
        ).all()
        
        group_names = []
        for eg in event_groups:
            group = db.query(Group).filter(Group.id == eg.group_id).first()
            if group:
                group_names.append(group.name)
        
        time_diff = event.start_datetime - now
        hours = int(time_diff.total_seconds() // 3600)
        minutes = int((time_diff.total_seconds() % 3600) // 60)
        
        logger.info(f"{i}. Event ID: {event.id}")
        logger.info(f"   Title: {event.title}")
        logger.info(f"   Type: {event.event_type}")
        logger.info(f"   Start: {event.start_datetime.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        logger.info(f"   Time until: {hours}h {minutes}m")
        logger.info(f"   Groups: {', '.join(group_names) if group_names else 'None'}")
        logger.info(f"   Is recurring: {event.is_recurring}")
        logger.info("")
    
    # Also check Tuesday 11:22 specifically
    logger.info("=" * 80)
    logger.info("CHECKING TUESDAY EVENTS AROUND 11:22")
    logger.info("=" * 80)
    
    # Find next Tuesday
    days_until_tuesday = (1 - now.weekday()) % 7  # Tuesday is 1
    if days_until_tuesday == 0 and now.hour > 11:
        days_until_tuesday = 7
    
    next_tuesday = now + timedelta(days=days_until_tuesday)
    tuesday_morning = datetime(next_tuesday.year, next_tuesday.month, next_tuesday.day, 11, 0)
    tuesday_afternoon = datetime(next_tuesday.year, next_tuesday.month, next_tuesday.day, 12, 0)
    
    logger.info(f"Searching between {tuesday_morning} and {tuesday_afternoon} UTC")
    
    tuesday_events = db.query(Event).filter(
        Event.start_datetime >= tuesday_morning,
        Event.start_datetime <= tuesday_afternoon,
        Event.is_active == True
    ).all()
    
    logger.info(f"Found {len(tuesday_events)} events on Tuesday around 11:22")
    
    for event in tuesday_events:
        event_groups = db.query(EventGroup).filter(
            EventGroup.event_id == event.id
        ).all()
        
        group_names = []
        for eg in event_groups:
            group = db.query(Group).filter(Group.id == eg.group_id).first()
            if group:
                group_names.append(group.name)
        
        logger.info(f"\n   Event ID: {event.id}")
        logger.info(f"   Title: {event.title}")
        logger.info(f"   Start: {event.start_datetime}")
        logger.info(f"   Groups: {', '.join(group_names)}")
    
finally:
    db.close()
