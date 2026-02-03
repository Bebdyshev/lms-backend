#!/usr/bin/env python3
"""
Diagnostic script to debug lesson reminder scheduler
Shows current time, schedules in database, and when reminders should be sent
"""
import logging
from datetime import datetime, timedelta
from src.config import SessionLocal
from src.schemas.models import LessonSchedule, Lesson, Group

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def diagnose_scheduler():
    """Diagnose lesson reminder scheduler"""
    
    logger.info("=" * 80)
    logger.info("🔍 LESSON REMINDER SCHEDULER DIAGNOSTICS")
    logger.info("=" * 80)
    
    db = SessionLocal()
    try:
        now_utc = datetime.utcnow()
        logger.info(f"\n⏰ CURRENT TIME:")
        logger.info(f"   UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"   Local (estimate): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        reminder_start = now_utc + timedelta(minutes=28)
        reminder_end = now_utc + timedelta(minutes=32)
        logger.info(f"\n🎯 REMINDER WINDOW (28-32 minutes from now):")
        logger.info(f"   Start: {reminder_start.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        logger.info(f"   End:   {reminder_end.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        # Get all active schedules
        all_schedules = db.query(LessonSchedule).filter(
            LessonSchedule.is_active == True
        ).order_by(LessonSchedule.scheduled_at).all()
        
        logger.info(f"\n📋 ALL ACTIVE SCHEDULES: {len(all_schedules)} found")
        logger.info("=" * 80)
        
        if not all_schedules:
            logger.warning("⚠️  No active schedules found in database!")
        else:
            for i, schedule in enumerate(all_schedules, 1):
                # Get lesson and group info
                lesson = db.query(Lesson).filter(Lesson.id == schedule.lesson_id).first()
                group = db.query(Group).filter(Group.id == schedule.group_id).first()
                
                lesson_title = lesson.title if lesson else "Unknown Lesson"
                group_name = group.name if group else "Unknown Group"
                
                # Calculate time difference
                time_diff = schedule.scheduled_at - now_utc
                hours = int(time_diff.total_seconds() // 3600)
                minutes = int((time_diff.total_seconds() % 3600) // 60)
                
                # Check if in reminder window
                in_window = reminder_start <= schedule.scheduled_at <= reminder_end
                
                status = "🔔 IN REMINDER WINDOW" if in_window else ""
                
                logger.info(f"\n{i}. Schedule ID: {schedule.id} {status}")
                logger.info(f"   Lesson: {lesson_title}")
                logger.info(f"   Group: {group_name}")
                logger.info(f"   Scheduled: {schedule.scheduled_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                logger.info(f"   Time until lesson: {hours}h {minutes}m")
                
                if time_diff.total_seconds() < 0:
                    logger.info(f"   ⚠️  This lesson is in the PAST")
                elif in_window:
                    logger.info(f"   ✅ Should send reminder NOW")
        
        # Check for schedules in the reminder window
        logger.info("\n" + "=" * 80)
        upcoming_schedules = db.query(LessonSchedule).filter(
            LessonSchedule.is_active == True,
            LessonSchedule.scheduled_at >= reminder_start,
            LessonSchedule.scheduled_at <= reminder_end
        ).all()
        
        logger.info(f"📨 SCHEDULES IN REMINDER WINDOW: {len(upcoming_schedules)}")
        
        if upcoming_schedules:
            logger.info("   These should trigger email reminders:")
            for schedule in upcoming_schedules:
                lesson = db.query(Lesson).filter(Lesson.id == schedule.lesson_id).first()
                group = db.query(Group).filter(Group.id == schedule.group_id).first()
                logger.info(f"   - {schedule.id}: {lesson.title if lesson else 'Unknown'} "
                          f"at {schedule.scheduled_at.strftime('%H:%M')}")
        else:
            logger.info("   No schedules in the reminder window")
        
        # Check future schedules
        logger.info("\n" + "=" * 80)
        next_24h = now_utc + timedelta(hours=24)
        future_schedules = db.query(LessonSchedule).filter(
            LessonSchedule.is_active == True,
            LessonSchedule.scheduled_at > now_utc,
            LessonSchedule.scheduled_at <= next_24h
        ).order_by(LessonSchedule.scheduled_at).limit(5).all()
        
        logger.info(f"🔮 NEXT SCHEDULES (within 24h): {len(future_schedules)}")
        for schedule in future_schedules:
            lesson = db.query(Lesson).filter(Lesson.id == schedule.lesson_id).first()
            group = db.query(Group).filter(Group.id == schedule.group_id).first()
            
            time_diff = schedule.scheduled_at - now_utc
            hours = int(time_diff.total_seconds() // 3600)
            minutes = int((time_diff.total_seconds() % 3600) // 60)
            
            logger.info(f"   - {schedule.scheduled_at.strftime('%Y-%m-%d %H:%M')} UTC "
                       f"(in {hours}h {minutes}m): {lesson.title if lesson else 'Unknown'}")
        
        # Show environment info
        logger.info("\n" + "=" * 80)
        logger.info("🔧 CONFIGURATION:")
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        resend_key = os.getenv('RESEND_API_KEY')
        logger.info(f"   RESEND_API_KEY: {'✅ Set' if resend_key else '❌ Not set'}")
        
        if resend_key:
            logger.info(f"   Key length: {len(resend_key)} characters")
            logger.info(f"   Key preview: {resend_key[:10]}...")
        
        email_sender = os.getenv('EMAIL_SENDER', 'noreply@mail.mastereducation.kz')
        logger.info(f"   EMAIL_SENDER: {email_sender}")
        
        # Check if scheduler is running (this script can't detect it, but we can check logs)
        logger.info("\n📊 SCHEDULER STATUS:")
        logger.info("   Check your FastAPI logs for:")
        logger.info("   - '✅ Lesson reminder scheduler started'")
        logger.info("   - '📧 Lesson reminder scheduler is running...'")
        logger.info("   - Periodic 'Checking for lessons' messages (every 60 seconds)")
        
    except Exception as e:
        logger.error(f"\n❌ Error during diagnostics: {e}", exc_info=True)
    finally:
        db.close()
        
    logger.info("\n" + "=" * 80)
    logger.info("🏁 DIAGNOSTICS COMPLETED")
    logger.info("=" * 80)
    
    logger.info("\n💡 TIPS:")
    logger.info("   - Schedules are stored in UTC time")
    logger.info("   - Scheduler checks every 60 seconds")
    logger.info("   - Reminders sent 28-32 minutes before scheduled_at")
    logger.info("   - Check your timezone when creating schedules!")
    logger.info("   - Restart uvicorn to see '✅ Lesson reminder scheduler started' message")

if __name__ == "__main__":
    diagnose_scheduler()
