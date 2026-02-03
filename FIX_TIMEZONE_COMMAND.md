# Fix Event Timezone on Production

## Problem
Events were saved with Kazakhstan time (GMT+5) but stored as UTC.
For example: A lesson at 19:00 Kazakhstan time was saved as 19:00 UTC instead of 14:00 UTC.

## Solution
Subtract 5 hours from all event start_datetime and end_datetime fields.

## Run on Production Server

```bash
# SSH to production server
ssh user@your-server

# Navigate to backend directory
cd /path/to/lms/backend

# Run the fix script
docker compose exec -T backend python fix_event_timezone.py
```

## Or run directly with docker compose exec:

```bash
docker compose exec -T backend python -c "
from datetime import timedelta
from src.config import SessionLocal
from src.schemas.models import Event

db = SessionLocal()
KZ_OFFSET = timedelta(hours=5)

events = db.query(Event).filter(
    Event.is_active == True,
    Event.event_type == 'class'
).all()

print(f'Fixing {len(events)} events...')

for event in events:
    event.start_datetime = event.start_datetime - KZ_OFFSET
    event.end_datetime = event.end_datetime - KZ_OFFSET

db.commit()
print('Done!')
db.close()
"
```

## Verify After Fix

```bash
docker compose exec -T backend python -c "
from datetime import datetime, timedelta
from src.config import SessionLocal
from src.schemas.models import Event

db = SessionLocal()
now = datetime.utcnow()
KZ_OFFSET = timedelta(hours=5)

upcoming = db.query(Event).filter(
    Event.is_active == True,
    Event.event_type == 'class',
    Event.start_datetime >= now
).order_by(Event.start_datetime).limit(3).all()

for event in upcoming:
    kz_time = event.start_datetime + KZ_OFFSET
    print(f'{event.title}')
    print(f'  UTC: {event.start_datetime.strftime(\"%H:%M\")}')
    print(f'  KZ:  {kz_time.strftime(\"%H:%M\")}')
    print()

db.close()
"
```
