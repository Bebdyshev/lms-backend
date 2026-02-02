#!/usr/bin/env python3
"""Test /my events endpoint to see what it returns"""
import sys
sys.path.insert(0, 'src')
from config import SessionLocal
from src.schemas.models import Event, Group, GroupStudent, LessonSchedule
from datetime import datetime, timedelta

db = SessionLocal()

# Find a student with groups
student = db.query(GroupStudent).first()
if not student:
    print("No students found")
    db.close()
    sys.exit(1)

student_id = student.student_id
group_id = student.group_id

print(f"Testing for student_id={student_id}, group_id={group_id}")

# Check class events
class_events_count = db.query(Event).filter(
    Event.event_type == 'class',
    Event.is_active == True
).count()
print(f"\nActive class events in DB: {class_events_count}")

# Check LessonSchedule for this group
start_date = datetime.now() - timedelta(days=21)
end_date = datetime.now() + timedelta(days=21)

schedules = db.query(LessonSchedule).filter(
    LessonSchedule.group_id == group_id,
    LessonSchedule.is_active == True,
    LessonSchedule.scheduled_at >= start_date,
    LessonSchedule.scheduled_at <= end_date
).count()

print(f"LessonSchedules for group {group_id} (±3 weeks): {schedules}")

# Now simulate what /my endpoint would return
from src.services.event_service import EventService

virtual_events = EventService.expand_recurring_events(
    db=db,
    start_date=start_date,
    end_date=end_date,
    group_ids=[group_id],
    course_ids=[],
    skip_class_events=True  # This is the default
)

class_virtual = [e for e in virtual_events if e.event_type == 'class']
print(f"\nVirtual class events from EventService: {len(class_virtual)}")

if class_virtual:
    print("\nFirst 5 virtual class events:")
    for e in class_virtual[:5]:
        print(f"  id={e.id}, title={e.title}, start={e.start_datetime}")
else:
    print("\n⚠️  No virtual class events! This is the problem.")
    print("LessonSchedule events are not being converted to virtual events.")

db.close()
