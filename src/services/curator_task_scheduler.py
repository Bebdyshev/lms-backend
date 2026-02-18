"""
Curator Task Scheduler
Periodically checks for recurring task templates and generates task instances.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from croniter import croniter  # Not used yet, but good for future
import pytz

from src.config import SessionLocal
from src.schemas.models import (
    CuratorTaskTemplate, CuratorTaskInstance,
    UserInDB, Group, GroupStudent
)

logger = logging.getLogger(__name__)

class CuratorTaskScheduler:
    """
    Background scheduler to generate recurring curator tasks.
    Runs every hour to check if new tasks need to be created based on templates.
    """
    
    def __init__(self, check_interval: int = 3600):
        """
        Initialize the scheduler
        Args:
            check_interval: How often to check (in seconds). Default: 1 hour.
        """
        self.check_interval = check_interval
        self.running = False
        self.thread = None
        
    def start(self):
        """Start the scheduler in a background thread"""
        if self.running:
            logger.warning("Curator task scheduler is already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("✅ Curator task scheduler started")
        
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("🛑 Curator task scheduler stopped")
        
    def _run(self):
        """Main scheduler loop"""
        logger.info(f"⏳ [SCHEDULER] Curator task scheduler started (interval: {self.check_interval}s)")
        
        # Initial check on startup
        try:
            self._check_and_create_tasks()
        except Exception as e:
            logger.error(f"❌ [SCHEDULER] Error in initial curator task check: {e}", exc_info=True)

        while self.running:
            time.sleep(self.check_interval)
            if not self.running:
                break
                
            try:
                self._check_and_create_tasks()
            except Exception as e:
                logger.error(f"❌ [SCHEDULER] Error in curator task check: {e}", exc_info=True)
    
    def _check_and_create_tasks(self):
        """Check recurring templates and create instances if needed."""
        db = SessionLocal()
        try:
            # Current time in Almaty (default for our system)
            tz = pytz.timezone("Asia/Almaty")
            now_almaty = datetime.now(tz)
            
            # ISO Week (e.g., "2026-W08")
            year, week, _ = now_almaty.isocalendar()
            week_ref = f"{year}-W{week:02d}"
            
            # Get active recurring templates
            templates = db.query(CuratorTaskTemplate).filter(
                CuratorTaskTemplate.is_active == True,
                CuratorTaskTemplate.recurrence_rule.isnot(None)
            ).all()
            
            created_count = 0
            
            for tmpl in templates:
                rule = tmpl.recurrence_rule
                if not rule:
                    continue
                
                # Check if today is the day (simple check)
                # rule example: {"day_of_week": "monday", "time": "09:00"}
                target_day = rule.get("day_of_week", "").lower()
                current_day = now_almaty.strftime("%A").lower()
                
                if target_day != current_day:
                    continue
                
                # Check time (allow creation if we passed the time today)
                # We don't want to double-create, so we rely on week_ref uniqueness logic below
                target_time_str = rule.get("time", "09:00")
                try:
                    target_hour = int(target_time_str.split(":")[0])
                    if now_almaty.hour < target_hour:
                        continue # Too early
                except:
                    pass

                # Calculate Due Date
                due_date = None
                if tmpl.deadline_rule:
                    due_date = self._calculate_due_date(now_almaty, tmpl.deadline_rule)
                
                # SCOPE: STUDENT
                if tmpl.scope == "student":
                    # Find all students with curators
                    # We iterate efficiently via Groups
                    groups = db.query(Group).filter(Group.curator_id.isnot(None), Group.is_active == True).all()
                    
                    for group in groups:
                        students = db.query(UserInDB).join(GroupStudent).filter(
                            GroupStudent.group_id == group.id,
                            UserInDB.is_active == True
                        ).all()
                        
                        for student in students:
                            # Check if task already exists for this week
                            exists = db.query(CuratorTaskInstance).filter(
                                CuratorTaskInstance.template_id == tmpl.id,
                                CuratorTaskInstance.student_id == student.id,
                                CuratorTaskInstance.week_reference == week_ref
                            ).first()
                            
                            if not exists:
                                self._create_instance(db, tmpl, group.curator_id, student_id=student.id, group_id=group.id, due_date=due_date, week_ref=week_ref)
                                created_count += 1

                # SCOPE: GROUP
                elif tmpl.scope == "group":
                    groups = db.query(Group).filter(Group.curator_id.isnot(None), Group.is_active == True).all()
                    
                    for group in groups:
                        # Check existance
                        exists = db.query(CuratorTaskInstance).filter(
                            CuratorTaskInstance.template_id == tmpl.id,
                            CuratorTaskInstance.group_id == group.id,
                            CuratorTaskInstance.week_reference == week_ref
                        ).first()
                        
                        if not exists:
                            self._create_instance(db, tmpl, group.curator_id, group_id=group.id, due_date=due_date, week_ref=week_ref)
                            created_count += 1
            
            if created_count > 0:
                logger.info(f"✨ [SCHEDULER] Created {created_count} recurring curator tasks for {week_ref}")
                db.commit()
                
        except Exception as e:
            logger.error(f"❌ [SCHEDULER] Error creating tasks: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

    def _calculate_due_date(self, start_dt: datetime, rule: dict) -> datetime:
        """Calculate absolute due date based on rule and start time."""
        # start_dt is timezone aware (Almaty)
        due = start_dt
        
        # Add offset days/hours
        if "offset_days" in rule:
            due += timedelta(days=rule["offset_days"])
        if "offset_hours" in rule:
            due += timedelta(hours=rule["offset_hours"])
            
        # Set specific day of week if needed (e.g. deadline is Next Sunday)
        if "day_of_week" in rule:
            target_day_idx = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6
            }.get(rule["day_of_week"].lower())
            
            if target_day_idx is not None:
                current_day_idx = start_dt.weekday()
                days_ahead = target_day_idx - current_day_idx
                if days_ahead <= 0: # Target day already passed this week, move to next week? 
                    # Usually deadlines are later in the week. If we generated task on Monday and deadline is Sunday, days_ahead = 6.
                    # If generated on Monday and deadline was LAST Sunday, we probably mean NEXT Sunday.
                    if days_ahead < 0:
                        days_ahead += 7
                due += timedelta(days=days_ahead)

        # Set specific time
        if "time" in rule:
            try:
                h, m = map(int, rule["time"].split(":"))
                due = due.replace(hour=h, minute=m, second=0, microsecond=0)
            except:
                pass
                
        # Return as UTC for DB storage
        return due.astimezone(timezone.utc)

    def _create_instance(self, db, template, curator_id, student_id=None, group_id=None, due_date=None, week_ref=None):
        inst = CuratorTaskInstance(
            template_id=template.id,
            curator_id=curator_id,
            student_id=student_id,
            group_id=group_id,
            status="pending",
            due_date=due_date,
            week_reference=week_ref
        )
        db.add(inst)


# Global scheduler instance
_scheduler: Optional[CuratorTaskScheduler] = None

def get_scheduler() -> CuratorTaskScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CuratorTaskScheduler(check_interval=3600)  # Check every hour
    return _scheduler

def start_curator_task_scheduler():
    scheduler = get_scheduler()
    scheduler.start()

def stop_curator_task_scheduler():
    scheduler = get_scheduler()
    scheduler.stop()
