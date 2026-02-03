"""
Lesson Reminder Scheduler
Periodically checks for upcoming lessons and sends email reminders 30 minutes before.
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session

from src.config import SessionLocal
from src.schemas.models import LessonSchedule, UserInDB, Group, Lesson, GroupStudent
from src.services.email_service import send_lesson_reminder_notification

logger = logging.getLogger(__name__)


class LessonReminderScheduler:
    """Background scheduler to send lesson reminders"""
    
    def __init__(self, check_interval: int = 60):
        """
        Initialize the scheduler
        
        Args:
            check_interval: How often to check for upcoming lessons (in seconds)
        """
        self.check_interval = check_interval
        self.running = False
        self.thread = None
        self.sent_reminders = set()  # Track sent reminders to avoid duplicates
        
    def start(self):
        """Start the scheduler in a background thread"""
        if self.running:
            logger.warning("Lesson reminder scheduler is already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("✅ Lesson reminder scheduler started")
        
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("🛑 Lesson reminder scheduler stopped")
        
    def _run(self):
        """Main scheduler loop"""
        logger.info("📧 Lesson reminder scheduler is running...")
        
        while self.running:
            try:
                self._check_and_send_reminders()
            except Exception as e:
                logger.error(f"❌ Error in lesson reminder scheduler: {e}", exc_info=True)
            
            # Wait for next check
            time.sleep(self.check_interval)
    
    def _check_and_send_reminders(self):
        """Check for upcoming lessons and send reminders"""
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            # Look for lessons starting in 28-32 minutes (to account for check interval)
            reminder_time_start = now + timedelta(minutes=28)
            reminder_time_end = now + timedelta(minutes=32)
            
            # Query for active lesson schedules in the reminder window
            upcoming_schedules = db.query(LessonSchedule).filter(
                LessonSchedule.is_active == True,
                LessonSchedule.scheduled_at >= reminder_time_start,
                LessonSchedule.scheduled_at <= reminder_time_end
            ).all()
            
            if not upcoming_schedules:
                return
                
            logger.info(f"📅 Found {len(upcoming_schedules)} upcoming lessons for reminders")
            
            for schedule in upcoming_schedules:
                # Create unique key to avoid duplicate sends
                reminder_key = f"{schedule.id}_{schedule.scheduled_at.isoformat()}"
                
                if reminder_key in self.sent_reminders:
                    continue  # Already sent reminder for this lesson
                
                # Send reminders for this lesson
                success = self._send_lesson_reminders(db, schedule)
                
                if success:
                    self.sent_reminders.add(reminder_key)
                    
                    # Clean up old entries from sent_reminders to prevent memory bloat
                    # Keep only reminders from last 24 hours
                    cutoff_time = now - timedelta(hours=24)
                    self.sent_reminders = {
                        key for key in self.sent_reminders 
                        if not key.split('_')[1] or 
                        datetime.fromisoformat(key.split('_')[1]) > cutoff_time
                    }
                    
        except Exception as e:
            logger.error(f"❌ Error checking for lesson reminders: {e}", exc_info=True)
        finally:
            db.close()
    
    def _send_lesson_reminders(self, db: Session, schedule: LessonSchedule) -> bool:
        """
        Send reminders for a specific lesson schedule
        
        Args:
            db: Database session
            schedule: LessonSchedule to send reminders for
            
        Returns:
            True if reminders sent successfully
        """
        try:
            # Get lesson details
            lesson = db.query(Lesson).filter(Lesson.id == schedule.lesson_id).first()
            if not lesson:
                logger.warning(f"⚠️  Lesson not found for schedule {schedule.id}")
                return False
            
            # Get group details
            group = db.query(Group).filter(Group.id == schedule.group_id).first()
            if not group:
                logger.warning(f"⚠️  Group not found for schedule {schedule.id}")
                return False
            
            # Format lesson datetime for display
            lesson_datetime_str = schedule.scheduled_at.strftime("%d.%m.%Y в %H:%M")
            
            # Get all students in the group
            students = db.query(UserInDB).join(
                GroupStudent, UserInDB.id == GroupStudent.user_id
            ).filter(
                GroupStudent.group_id == group.id,
                UserInDB.is_active == True,
                UserInDB.email.isnot(None)
            ).all()
            
            # Get teacher (curator) of the group
            teacher = None
            if group.curator_id:
                teacher = db.query(UserInDB).filter(
                    UserInDB.id == group.curator_id,
                    UserInDB.is_active == True,
                    UserInDB.email.isnot(None)
                ).first()
            
            sent_count = 0
            
            # Send reminders to all students
            for student in students:
                try:
                    result = send_lesson_reminder_notification(
                        to_email=student.email,
                        recipient_name=student.name or student.email.split('@')[0],
                        lesson_title=lesson.title,
                        lesson_datetime=lesson_datetime_str,
                        group_name=group.name,
                        role="student"
                    )
                    if result:
                        sent_count += 1
                except Exception as e:
                    logger.error(f"❌ Failed to send reminder to student {student.email}: {e}")
            
            # Send reminder to teacher
            if teacher:
                try:
                    result = send_lesson_reminder_notification(
                        to_email=teacher.email,
                        recipient_name=teacher.name or teacher.email.split('@')[0],
                        lesson_title=lesson.title,
                        lesson_datetime=lesson_datetime_str,
                        group_name=group.name,
                        role="teacher"
                    )
                    if result:
                        sent_count += 1
                except Exception as e:
                    logger.error(f"❌ Failed to send reminder to teacher {teacher.email}: {e}")
            
            logger.info(
                f"✅ Sent {sent_count} reminders for lesson '{lesson.title}' "
                f"(Group: {group.name}, Time: {lesson_datetime_str})"
            )
            
            return sent_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error sending lesson reminders for schedule {schedule.id}: {e}", exc_info=True)
            return False


# Global scheduler instance
_scheduler: LessonReminderScheduler = None


def get_scheduler() -> LessonReminderScheduler:
    """Get or create the global scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = LessonReminderScheduler(check_interval=60)  # Check every minute
    return _scheduler


def start_lesson_reminder_scheduler():
    """Start the lesson reminder scheduler"""
    scheduler = get_scheduler()
    scheduler.start()


def stop_lesson_reminder_scheduler():
    """Stop the lesson reminder scheduler"""
    scheduler = get_scheduler()
    scheduler.stop()
