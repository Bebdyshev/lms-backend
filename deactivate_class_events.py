#!/usr/bin/env python3
"""Deactivate old class events so LessonSchedule events can show"""
import sys
sys.path.insert(0, 'src')
from config import SessionLocal
from src.schemas.models import Event

db = SessionLocal()

# Deactivate all class events
class_events = db.query(Event).filter(
    Event.event_type == 'class',
    Event.is_active == True
).all()

count = len(class_events)
print(f'Found {count} active class events')

if count > 0:
    confirm = input(f'Deactivate all {count} class events? (yes/no): ')
    if confirm.lower() == 'yes':
        for event in class_events:
            event.is_active = False
        db.commit()
        print(f'✅ Deactivated {count} class events')
        print('Calendar will now show LessonSchedule events with correct lesson numbers')
    else:
        print('Cancelled')
else:
    print('✅ No class events to deactivate')

db.close()
