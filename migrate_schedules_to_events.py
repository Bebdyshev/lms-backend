"""
Migration script to convert LessonSchedule entries to real Event entries.
This allows us to deprecate LessonSchedule and use only Events for calendar.

Run with: python migrate_schedules_to_events.py
"""

from src.config import SessionLocal
from src.schemas.models import LessonSchedule, Event, EventGroup, Group
from datetime import timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_schedules_to_events(dry_run: bool = True):
    """
    Convert all LessonSchedule entries to Event entries.
    
    Args:
        dry_run: If True, only show what would be created without making changes
    """
    db = SessionLocal()
    
    try:
        # Get all active schedules
        schedules = db.query(LessonSchedule).filter(
            LessonSchedule.is_active == True
        ).order_by(LessonSchedule.group_id, LessonSchedule.scheduled_at).all()
        
        logger.info(f"Found {len(schedules)} LessonSchedule entries to migrate")
        
        # Track what we'll create
        events_to_create = []
        skipped = 0
        
        for sched in schedules:
            # Check if an event already exists for this group + time
            existing = db.query(Event).join(EventGroup).filter(
                EventGroup.group_id == sched.group_id,
                Event.start_datetime == sched.scheduled_at,
                Event.event_type == "class",
                Event.is_active == True
            ).first()
            
            if existing:
                logger.debug(f"Skipping schedule {sched.id} - Event already exists (ID: {existing.id})")
                skipped += 1
                continue
            
            # Get group info
            group = db.query(Group).filter(Group.id == sched.group_id).first()
            if not group:
                logger.warning(f"Skipping schedule {sched.id} - Group {sched.group_id} not found")
                skipped += 1
                continue
            
            # Build event title
            lesson_title = sched.lesson.title if sched.lesson else f"Lesson {sched.id}"
            event_title = f"{group.name}: {lesson_title}"
            
            # Determine creator (use group's teacher)
            creator_id = group.teacher_id
            if not creator_id:
                # Fallback to admin
                from src.schemas.models import UserInDB
                admin = db.query(UserInDB).filter(UserInDB.role == "admin").first()
                creator_id = admin.id if admin else 1
            
            event_data = {
                "title": event_title,
                "description": f"Lesson: {lesson_title}",
                "event_type": "class",
                "start_datetime": sched.scheduled_at,
                "end_datetime": sched.scheduled_at + timedelta(minutes=90),  # Default 1.5h
                "location": "Online",
                "is_online": True,
                "meeting_url": "",
                "is_recurring": False,
                "teacher_id": group.teacher_id,
                "created_by": creator_id,
                "is_active": True,
                "group_id": sched.group_id,
                "schedule_id": sched.id  # Reference for tracking
            }
            
            events_to_create.append(event_data)
        
        logger.info(f"Events to create: {len(events_to_create)}")
        logger.info(f"Skipped (already exist): {skipped}")
        
        if dry_run:
            logger.info("\n=== DRY RUN - No changes made ===")
            logger.info("First 10 events that would be created:")
            for i, event_data in enumerate(events_to_create[:10]):
                logger.info(f"  {i+1}. {event_data['title']} at {event_data['start_datetime']}")
            if len(events_to_create) > 10:
                logger.info(f"  ... and {len(events_to_create) - 10} more")
            return
        
        # Actually create the events
        logger.info("\n=== Creating Events ===")
        created_count = 0
        
        for event_data in events_to_create:
            group_id = event_data.pop("group_id")
            event_data.pop("schedule_id")  # Remove tracking field
            
            new_event = Event(**event_data)
            db.add(new_event)
            db.flush()  # Get the ID
            
            # Create EventGroup link
            event_group = EventGroup(event_id=new_event.id, group_id=group_id)
            db.add(event_group)
            
            created_count += 1
            
            if created_count % 50 == 0:
                logger.info(f"Created {created_count} events...")
        
        db.commit()
        logger.info(f"\n✅ Successfully created {created_count} events!")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error during migration: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    dry_run = "--execute" not in sys.argv
    
    if dry_run:
        print("=" * 60)
        print("DRY RUN MODE - No changes will be made")
        print("Run with --execute to actually create events")
        print("=" * 60)
    else:
        print("=" * 60)
        print("EXECUTE MODE - Events will be created!")
        print("=" * 60)
        confirm = input("Are you sure? (yes/no): ")
        if confirm.lower() != "yes":
            print("Aborted.")
            sys.exit(0)
    
    migrate_schedules_to_events(dry_run=dry_run)
