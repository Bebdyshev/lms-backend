
from datetime import datetime, date, timedelta
import calendar

# Mock objects to simulate the backend environment
class MockEvent:
    def __init__(self, start_datetime, end_datetime):
        self.title = "Weekly test"
        self.description = "dasdas"
        self.event_type = "weekly_test"
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

# The function to test (copied from admin.py)
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
    
    print(f"Loop start condition: current_start.date() ({current_start.date()}) <= recurrence_end_date ({event_data.recurrence_end_date})")
    
    while current_start.date() <= event_data.recurrence_end_date:
        print(f"Creating recurring event: {current_start} - {current_end}")
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

async def run_debug():
    print("Debugging Recurrence Logic...")
    
    # Parameters from user report
    # 05.12.2025, 00:00 - 07.12.2025, 00:00
    start = datetime(2025, 12, 5, 0, 0)
    end = datetime(2025, 12, 7, 0, 0)
    
    # User said "Recurring", but didn't specify end date in the text provided.
    # However, for it to repeat "once" (meaning 1 extra time?), the end date must cover at least one period.
    # Weekly recurrence. Next event should be 12.12.2025.
    
    # Let's assume recurrence end date is same as end date (common mistake) or slightly after
    # Case 1: Recurrence end date is same as event end date (07.12.2025)
    print("\nCase 1: Recurrence end date = Event end date (07.12.2025)")
    recurrence_end_1 = date(2025, 12, 7)
    
    base_event_1 = MockEvent(start, end)
    event_data_1 = MockEventData("weekly", recurrence_end_1, [])
    db_1 = MockDB()
    
    await create_recurring_events(db_1, base_event_1, event_data_1)
    print(f"Generated {len(db_1.events)} additional events")
    
    # Case 2: Recurrence end date is one week later (14.12.2025)
    print("\nCase 2: Recurrence end date = One week later (14.12.2025)")
    recurrence_end_2 = date(2025, 12, 14)
    
    base_event_2 = MockEvent(start, end)
    event_data_2 = MockEventData("weekly", recurrence_end_2, [])
    db_2 = MockDB()
    
    await create_recurring_events(db_2, base_event_2, event_data_2)
    print(f"Generated {len(db_2.events)} additional events")

if __name__ == "__main__":
    asyncio.run(run_debug())
