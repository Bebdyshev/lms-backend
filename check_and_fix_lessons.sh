#!/bin/bash
# Check and fix lesson numbering in calendar
# Run this on the server with: bash check_and_fix_lessons.sh

echo "================================================================"
echo "  Checking Class Events in Database"
echo "================================================================"
echo ""

# Check for class events
docker compose exec -T web python3 -c "
import sys
sys.path.insert(0, 'src')
from config import SessionLocal
from src.schemas.models import Event

db = SessionLocal()

class_events_count = db.query(Event).filter(
    Event.event_type == 'class',
    Event.is_active == True
).count()

print(f'Total active class events: {class_events_count}')

if class_events_count > 0:
    print('\n⚠️  Found class events in database!')
    print('These are showing instead of LessonSchedule events.')
    
    class_events = db.query(Event).filter(
        Event.event_type == 'class',
        Event.is_active == True
    ).limit(10).all()
    
    print('\nFirst 10 class events:')
    for e in class_events:
        print(f'  id={e.id}, title={e.title[:50]}, start={e.start_datetime}')
else:
    print('\n✅ No class events found')

db.close()
"

echo ""
echo "================================================================"
echo "  Do you want to deactivate all class events? (yes/no)"
echo "================================================================"
read -p "Answer: " answer

if [ "$answer" = "yes" ]; then
    echo ""
    echo "Deactivating class events..."
    
    docker compose exec -T web python3 -c "
import sys
sys.path.insert(0, 'src')
from config import SessionLocal
from src.schemas.models import Event

db = SessionLocal()

class_events = db.query(Event).filter(
    Event.event_type == 'class',
    Event.is_active == True
).all()

count = len(class_events)
for event in class_events:
    event.is_active = False

db.commit()
db.close()

print(f'✅ Deactivated {count} class events')
print('Calendar will now show LessonSchedule events with correct lesson numbers')
"
    
    echo ""
    echo "================================================================"
    echo "  ✅ Done! Refresh your calendar to see Lesson 1, 2, 3..."
    echo "================================================================"
else
    echo "Cancelled"
fi
