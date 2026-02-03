#!/usr/bin/env python3
"""
Test event reminders with the updated scheduler
"""
import logging
from datetime import datetime, timedelta
from src.config import SessionLocal
from src.schemas.models import Event
from src.services.lesson_reminder_scheduler import LessonReminderScheduler

# Setup logging to see all messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_event_reminders():
    """Test the event reminder system"""
    
    logger.info("=" * 80)
    logger.info("🧪 TESTING EVENT REMINDER SYSTEM")
    logger.info("=" * 80)
    
    db = SessionLocal()
    try:
        # Find upcoming events in the next hour
        logger.info("\n📋 Step 1: Finding upcoming class events...")
        
        now = datetime.utcnow()
        next_hour = now + timedelta(hours=1)
        
        upcoming_events = db.query(Event).filter(
            Event.is_active == True,
            Event.event_type == 'class',
            Event.start_datetime >= now,
            Event.start_datetime <= next_hour
        ).order_by(Event.start_datetime).all()
        
        if not upcoming_events:
            logger.error("❌ No upcoming class events found in the next hour!")
            logger.info("\nTry creating an event that starts within the next hour.")
            return
        
        logger.info(f"✅ Found {len(upcoming_events)} upcoming class event(s)")
        
        for event in upcoming_events:
            time_diff = event.start_datetime - now
            minutes = int(time_diff.total_seconds() / 60)
            logger.info(f"\n   Event ID {event.id}:")
            logger.info(f"   - Title: {event.title}")
            logger.info(f"   - Starts in: {minutes} minutes")
            logger.info(f"   - Time: {event.start_datetime.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        # Test with the first event
        test_event = upcoming_events[0]
        
        logger.info(f"\n📧 Step 2: Testing reminder send for event '{test_event.title}'...")
        logger.info("=" * 80)
        
        scheduler = LessonReminderScheduler()
        success = scheduler._send_event_reminders(db, test_event)
        
        logger.info("=" * 80)
        logger.info(f"\n📊 Result: {'✅ SUCCESS' if success else '❌ FAILED'}")
        
        if not success:
            logger.error("\n⚠️  Possible reasons for failure:")
            logger.error("   1. RESEND_API_KEY not set in .env")
            logger.error("   2. No students in the group")
            logger.error("   3. Students have no email addresses")
            logger.error("   4. Network connectivity issues")
            logger.error("   5. Resend API quota exceeded")
            logger.error("\nCheck the detailed logs above for more information.")
        else:
            logger.info("\n✅ Reminders sent successfully!")
            logger.info("   Check email inboxes for the reminder.")
        
    except Exception as e:
        logger.error(f"\n❌ Error during test: {e}", exc_info=True)
    finally:
        db.close()
        
    logger.info("\n" + "=" * 80)
    logger.info("🏁 TEST COMPLETED")
    logger.info("=" * 80)

if __name__ == "__main__":
    test_event_reminders()
