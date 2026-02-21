#!/bin/bash
# Check missed attendance logs details

echo "============================================================"
echo "Checking missed attendance logs details"
echo "============================================================"

docker compose exec backend python -c "
from src.config import get_db
from src.schemas.models import MissedAttendanceLog, Event, Group

db = next(get_db())
try:
    logs = db.query(MissedAttendanceLog).all()
    
    print(f'Total logs: {len(logs)}')
    print('')
    
    for log in logs:
        event = db.query(Event).filter(Event.id == log.event_id).first()
        group = db.query(Group).filter(Group.id == log.group_id).first()
        
        if event and group:
            print(f'Log ID: {log.id}')
            print(f'  Event: {event.title} (ID: {event.id})')
            print(f'  Group: {group.name} (ID: {group.id})')
            print(f'  Date: {event.start_datetime}')
            print(f'  Expected: {log.expected_count}, Recorded: {log.recorded_count_at_detection}')
            print(f'  Resolved: {\"Yes\" if log.resolved_at else \"No\"}')
            print('')
            
except Exception as e:
    print(f'Error: {e}')
finally:
    db.close()
"
