
from datetime import datetime, date, timedelta
import calendar

# Mock objects to simulate the backend environment
class MockEvent:
    def __init__(self, start_datetime, end_datetime):
        self.title = "Test Event"
        self.description = "Test Description"
        self.event_type = "class"
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self.location = "Test Location"
        self.is_online = True
        self.meeting_url = "http://test.com"
        self.created_by = 1
        self.max_participants = 10
        self.id = 1

class MockEventData:
    def __init__(self, recurrence_pattern, recurrence_end_date, group_ids):
        self.recurrence_pattern = recurrence_pattern
        self.recurrence_end_date = recurrence_end_date
        self.group_ids = group_ids

class MockDB:
    def __init__(self):
        self.events = []
    
    def add(self, item):
        if hasattr(item, 'title'): # It's an event
            item.id = len(self.events) + 2
            self.events.append(item)
    
    def flush(self):
        pass

# The function to test (copied from admin.py with minor adjustments for standalone run)
async def create_recurring_events(db, base_event, event_data):
    current_start = base_event.start_datetime
    current_end = base_event.end_datetime
    original_start_day = base_event.start_datetime.day
    original_end_day = base_event.end_datetime.day
    
    # Initial increment based on pattern
    if event_data.recurrence_pattern == "weekly":
        delta = timedelta(weeks=1)
        current_start += delta
        current_end += delta
    elif event_data.recurrence_pattern == "biweekly":
        delta = timedelta(weeks=2)
        current_start += delta
        current_end += delta
    elif event_data.recurrence_pattern == "daily":
        delta = timedelta(days=1)
        current_start += delta
        current_end += delta
    elif event_data.recurrence_pattern == "monthly":
        pass
    else:
        return

    # For monthly, we need to handle the first increment manually if we haven't already
    if event_data.recurrence_pattern == "monthly":
        # Add one month to start
        year = current_start.year + (current_start.month // 12)
        month = (current_start.month % 12) + 1
        day = min(original_start_day, calendar.monthrange(year, month)[1])
        current_start = current_start.replace(year=year, month=month, day=day)
        
        # Add one month to end
        year_end = current_end.year + (current_end.month // 12)
        month_end = (current_end.month % 12) + 1
        day_end = min(original_end_day, calendar.monthrange(year_end, month_end)[1])
        current_end = current_end.replace(year=year_end, month=month_end, day=day_end)
    
    while current_start.date() <= event_data.recurrence_end_date:
        # Create mock event instead of real Event model
        recurring_event = MockEvent(current_start, current_end)
        recurring_event.is_recurring = False
        
        db.add(recurring_event)
        
        # Increment for next iteration
        if event_data.recurrence_pattern == "monthly":
            # Increment start
            year = current_start.year + (current_start.month // 12)
            month = (current_start.month % 12) + 1
            day = min(original_start_day, calendar.monthrange(year, month)[1])
            current_start = current_start.replace(year=year, month=month, day=day)
            
            # Increment end
            year_end = current_end.year + (current_end.month // 12)
            month_end = (current_end.month % 12) + 1
            day_end = min(original_end_day, calendar.monthrange(year_end, month_end)[1])
            current_end = current_end.replace(year=year_end, month=month_end, day=day_end)
        else:
            current_start += delta
            current_end += delta

import asyncio

async def run_tests():
    print("Running Recurrence Tests...")
    
    # Test 1: Biweekly
    print("\nTest 1: Biweekly Recurrence")
    start = datetime(2023, 1, 1, 10, 0) # Jan 1st
    end = datetime(2023, 1, 1, 11, 0)
    recurrence_end = date(2023, 2, 1) # Should include Jan 15, Jan 29
    
    base_event = MockEvent(start, end)
    event_data = MockEventData("biweekly", recurrence_end, [])
    db = MockDB()
    
    await create_recurring_events(db, base_event, event_data)
    
    print(f"Generated {len(db.events)} events")
    for e in db.events:
        print(f"  - {e.start_datetime}")
    
    assert len(db.events) == 2
    assert db.events[0].start_datetime == datetime(2023, 1, 15, 10, 0)
    assert db.events[1].start_datetime == datetime(2023, 1, 29, 10, 0)
    print("Biweekly test passed!")

    # Test 2: Monthly
    print("\nTest 2: Monthly Recurrence")
    start = datetime(2023, 1, 31, 10, 0) # Jan 31st (Edge case)
    end = datetime(2023, 1, 31, 11, 0)
    recurrence_end = date(2023, 4, 1) # Should include Feb 28, Mar 31
    
    base_event = MockEvent(start, end)
    event_data = MockEventData("monthly", recurrence_end, [])
    db = MockDB()
    
    await create_recurring_events(db, base_event, event_data)
    
    print(f"Generated {len(db.events)} events")
    for e in db.events:
        print(f"  - {e.start_datetime}")
    
    assert len(db.events) == 2
    # Feb 2023 has 28 days
    assert db.events[0].start_datetime == datetime(2023, 2, 28, 10, 0)
    assert db.events[1].start_datetime == datetime(2023, 3, 31, 10, 0)
    print("Monthly test passed!")

if __name__ == "__main__":
    asyncio.run(run_tests())
