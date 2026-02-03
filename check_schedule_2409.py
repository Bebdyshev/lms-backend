#!/usr/bin/env python3
"""
Check specific schedule timezone
"""
import logging
from datetime import datetime
from src.config import SessionLocal
from src.schemas.models import LessonSchedule

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

db = SessionLocal()
try:
    schedule = db.query(LessonSchedule).filter(LessonSchedule.id == 2409).first()
    
    if schedule:
        logger.info(f"Schedule ID 2409:")
        logger.info(f"  scheduled_at (from DB): {schedule.scheduled_at}")
        logger.info(f"  scheduled_at repr: {repr(schedule.scheduled_at)}")
        logger.info(f"  tzinfo: {schedule.scheduled_at.tzinfo}")
        logger.info(f"  ISO format: {schedule.scheduled_at.isoformat()}")
        
        now_utc = datetime.utcnow()
        logger.info(f"\nCurrent time:")
        logger.info(f"  UTC now: {now_utc}")
        logger.info(f"  Local now: {datetime.now()}")
        
        diff = schedule.scheduled_at - now_utc
        logger.info(f"\nTime difference:")
        logger.info(f"  {diff.total_seconds() / 3600:.2f} hours")
        logger.info(f"  {diff.days} days")
    else:
        logger.error("Schedule 2409 not found!")
finally:
    db.close()
