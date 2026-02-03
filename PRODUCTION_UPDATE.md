# Production Update Instructions

## Required Steps After Deployment

### 1. Update .env file on production server

Add these missing environment variables to `/path/to/lms/backend/.env`:

```bash
# Email Configuration
EMAIL_SENDER=noreply@mail.mastereducation.kz
EMAIL_SENDER_NAME=MasterED Platform
LMS_URL=https://lms.mastereducation.kz/homework
```

### 2. Fix existing event timezones (ONE-TIME MIGRATION)

All existing events were stored incorrectly. They need to be converted from Kazakhstan time to UTC:

```bash
cd /path/to/lms/backend

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

### 3. Restart backend to apply new environment variables

```bash
cd /path/to/lms/backend
docker compose down
docker compose up -d
```

### 4. Verify email notifications work

Check logs for successful email sends:

```bash
docker compose logs -f backend | grep -i email
```

Should see:
```
✅ [EMAIL] Successfully sent to X recipient(s)
```

Instead of:
```
❌ [EMAIL] Failed to send email: 422 Client Error
```

### 5. Verify event times are correct

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

## Summary of Changes

### Timezone Fixes
- ✅ Backend converts user-input Kazakhstan time (GMT+5) to UTC for storage
- ✅ Frontend displays UTC times as Kazakhstan time
- ✅ Email reminders show Kazakhstan time
- ✅ Scheduler works in UTC (as it should)

### Email Configuration
- ✅ Added `EMAIL_SENDER` to docker-compose.yml
- ✅ Added `LMS_URL` to docker-compose.yml
- ✅ Fixed Resend API 422 error ("Invalid `from` field")

### Database
- ✅ All existing events migrated from incorrect KZ time to correct UTC
- ✅ All new events automatically stored in UTC

## Expected Behavior After Update

1. **User creates schedule at 19:00 Kazakhstan time**
   - Backend stores: 14:00 UTC
   - Frontend shows: 19:00 Kazakhstan
   - Email shows: 19:00 Kazakhstan

2. **Reminder scheduler at 18:30 UTC (23:30 Kazakhstan)**
   - Finds events starting at 19:00 UTC (00:00 Kazakhstan)
   - Sends email showing: "00:00 Kazakhstan time"

3. **All times consistent across**:
   - Calendar view
   - Event details
   - Email notifications
   - Reminder scheduler logs
