#!/usr/bin/env python3
"""
Fix Event timezones: Convert incorrectly stored Kazakhstan time to proper UTC
Events were saved as Kazakhstan time (GMT+5) but stored as if they were UTC.
This script subtracts 5 hours to convert them to proper UTC.
"""
from datetime import timedelta
from src.config import SessionLocal
from src.schemas.models import Event

def main():
    db = SessionLocal()
    
    # Kazakhstan offset
    KZ_OFFSET = timedelta(hours=5)
    
    # Get all active class events
    events = db.query(Event).filter(
        Event.is_active == True,
        Event.event_type == 'class'
    ).all()
    
    print(f'🔧 Fixing {len(events)} events...')
    print('   Converting Kazakhstan time to UTC (subtracting 5 hours)')
    print()
    
    updated_count = 0
    for event in events:
        old_start = event.start_datetime
        old_end = event.end_datetime
        
        # Subtract 5 hours to convert from incorrectly stored KZ time to proper UTC
        event.start_datetime = old_start - KZ_OFFSET
        event.end_datetime = old_end - KZ_OFFSET
        
        updated_count += 1
        
        if updated_count <= 5:  # Show first 5 as examples
            print(f'Event {event.id}: {event.title[:50]}')
            print(f'  Before: {old_start.strftime("%Y-%m-%d %H:%M")} - {old_end.strftime("%H:%M")}')
            print(f'  After:  {event.start_datetime.strftime("%Y-%m-%d %H:%M")} - {event.end_datetime.strftime("%H:%M")} UTC')
            print()
    
    db.commit()
    print(f'✅ Successfully updated {updated_count} events!')
    
    db.close()

if __name__ == "__main__":
    main()
