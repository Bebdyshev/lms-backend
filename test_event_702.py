#!/usr/bin/env python3
"""
Test reminder for specific event
"""
import logging
from src.config import SessionLocal
from src.schemas.models import Event
from src.services.lesson_reminder_scheduler import LessonReminderScheduler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

db = SessionLocal()
try:
    # Get event 702 (the one at 11:22 today)
    event = db.query(Event).filter(Event.id == 702).first()
    
    if not event:
        logger.error("Event 702 not found!")
    else:
        logger.info(f"Testing reminder for event: {event.title}")
        logger.info(f"Scheduled for: {event.start_datetime}")
        logger.info("=" * 80)
        
        scheduler = LessonReminderScheduler()
        success = scheduler._send_event_reminders(db, event)
        
        logger.info("=" * 80)
        if success:
            logger.info("✅ SUCCESS - Reminders sent!")
        else:
            logger.error("❌ FAILED - Check logs above")
finally:
    db.close()
