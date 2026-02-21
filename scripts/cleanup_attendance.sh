#!/bin/bash
# Cleanup old missed attendance logs before February 4, 2026

echo "============================================================"
echo "Cleaning up old missed attendance logs (before Feb 4, 2026)"
echo "============================================================"

docker compose exec backend python -c "
from datetime import datetime
from src.config import get_db
from src.schemas.models import MissedAttendanceLog, Event

db = next(get_db())
try:
    cutoff_date = datetime(2026, 2, 4, 0, 0, 0)
    
    # Get all logs
    all_logs = db.query(MissedAttendanceLog).all()
    print(f'Total missed attendance logs: {len(all_logs)}')
    
    # Step 1: Delete logs for events before cutoff
    deleted_old = 0
    for log in all_logs:
        event = db.query(Event).filter(Event.id == log.event_id).first()
        if event and event.end_datetime < cutoff_date:
            print(f'Deleting old log for event: {event.title} (ended: {event.end_datetime})')
            db.delete(log)
            deleted_old += 1
    
    db.commit()
    print(f'Deleted {deleted_old} old logs before cutoff')
    
    # Step 2: Remove duplicates by group_id + event date (keep newest event_id)
    all_logs = db.query(MissedAttendanceLog).all()
    seen = {}  # key: (group_id, date), value: log with max event_id
    
    for log in all_logs:
        event = db.query(Event).filter(Event.id == log.event_id).first()
        if event:
            key = (log.group_id, event.start_datetime)
            
            if key in seen:
                existing_log = seen[key]
                # Keep the one with larger event_id (newer)
                if log.event_id > existing_log.event_id:
                    # Delete old one, keep new
                    print(f'Deleting duplicate: event_id={existing_log.event_id} (keeping {log.event_id})')
                    db.delete(existing_log)
                    seen[key] = log
                else:
                    # Delete current, keep existing
                    print(f'Deleting duplicate: event_id={log.event_id} (keeping {existing_log.event_id})')
                    db.delete(log)
            else:
                seen[key] = log
    
    db.commit()
    
    remaining = db.query(MissedAttendanceLog).count()
    print(f'Remaining logs: {remaining}')
except Exception as e:
    db.rollback()
    print(f'Error: {e}')
    raise
finally:
    db.close()
"

echo "============================================================"
echo "Done!"
echo "============================================================"
