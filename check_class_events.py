#!/usr/bin/env python3
"""Check if there are old class events in the database"""
import sys
sys.path.insert(0, 'src')
from config import SessionLocal
from src.schemas.models import Event
from datetime import datetime

db = SessionLocal()

# Check if there are recurring 'class' events
class_events_count = db.query(Event).filter(
    Event.event_type == 'class',
    Event.is_active == True
).count()

print(f'Total active class events: {class_events_count}')

if class_events_count > 0:
    print('\n⚠️  Found class events in database!')
    print('These might be showing instead of virtual LessonSchedule events.')
    print('\nFirst 20 class events:')
    
    class_events = db.query(Event).filter(
        Event.event_type == 'class',
        Event.is_active == True
    ).limit(20).all()
    
    for e in class_events:
        print(f'  id={e.id}, title={e.title}, is_recurring={e.is_recurring}, start={e.start_datetime}')
    
    print('\n💡 Solution: Deactivate old class events')
    print('Run: python3 deactivate_class_events.py')
else:
    print('\n✅ No class events found - calendar should show LessonSchedule correctly')

db.close()
