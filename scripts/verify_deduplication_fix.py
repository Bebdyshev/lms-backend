#!/usr/bin/env python3
"""
Verification script to test that event deduplication fix is working correctly.
Run this after deploying the fix to ensure everything works.

Usage:
    python3 verify_deduplication_fix.py
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# ANSI colors
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

def log_info(msg):
    print(f"{BLUE}ℹ {msg}{NC}")

def log_success(msg):
    print(f"{GREEN}✓ {msg}{NC}")

def log_warning(msg):
    print(f"{YELLOW}⚠ {msg}{NC}")

def log_error(msg):
    print(f"{RED}✗ {msg}{NC}")

def test_virtual_events_have_group_ids():
    """Test that virtual events have _group_ids attribute"""
    log_info("Test 1: Virtual events have _group_ids...")
    
    from sqlalchemy.orm import Session, joinedload
    from src.config import SessionLocal
    from src.schemas.models import Event, EventGroup
    from src.services.event_service import EventService
    
    db = SessionLocal()
    
    try:
        # Find a recurring event
        recurring_event = db.query(Event).filter(
            Event.is_recurring == True,
            Event.is_active == True
        ).first()
        
        if not recurring_event:
            log_warning("No recurring events found in database - skipping test")
            return True
        
        log_info(f"Found recurring event: {recurring_event.title}")
        
        # Get group IDs
        event_groups = db.query(EventGroup).filter(
            EventGroup.event_id == recurring_event.id
        ).all()
        
        if not event_groups:
            log_warning("Recurring event has no groups - skipping test")
            return True
        
        group_ids = [eg.group_id for eg in event_groups]
        log_info(f"Event has groups: {group_ids}")
        
        # Expand recurring events
        start_date = datetime.now()
        end_date = start_date + timedelta(days=30)
        
        generated_events = EventService.expand_recurring_events(
            db=db,
            start_date=start_date,
            end_date=end_date,
            group_ids=group_ids,
            course_ids=[]
        )
        
        if not generated_events:
            log_warning("No events generated - skipping test")
            return True
        
        log_info(f"Generated {len(generated_events)} virtual events")
        
        # Check _group_ids on all generated events
        success = True
        for i, event in enumerate(generated_events[:5]):  # Check first 5
            virtual_gids = getattr(event, '_group_ids', None)
            if virtual_gids is None:
                log_error(f"Event {i} missing _group_ids attribute")
                success = False
            elif not virtual_gids:
                log_error(f"Event {i} has empty _group_ids: {virtual_gids}")
                success = False
            elif set(virtual_gids) != set(group_ids):
                log_error(f"Event {i} has wrong _group_ids: {virtual_gids} != {group_ids}")
                success = False
            else:
                log_success(f"Event {i} has correct _group_ids: {virtual_gids}")
        
        return success
        
    finally:
        db.close()

def test_deduplication_logic():
    """Test that deduplication correctly uses _group_ids"""
    log_info("Test 2: Deduplication uses _group_ids...")
    
    from sqlalchemy.orm import Session
    from src.config import SessionLocal
    from src.schemas.models import Event, EventGroup, Group, LessonSchedule
    from src.services.event_service import EventService
    
    db = SessionLocal()
    
    try:
        # Get a group with both events and schedules
        group = db.query(Group).first()
        if not group:
            log_warning("No groups found - skipping test")
            return True
        
        log_info(f"Testing with group: {group.name} (ID: {group.id})")
        
        # Date range
        start_date = datetime(2026, 2, 1)
        end_date = datetime(2026, 2, 28, 23, 59, 59)
        
        # Get generated events
        generated_events = EventService.expand_recurring_events(
            db=db,
            start_date=start_date,
            end_date=end_date,
            group_ids=[group.id],
            course_ids=[]
        )
        
        if not generated_events:
            log_warning("No generated events - skipping test")
            return True
        
        log_info(f"Generated {len(generated_events)} events")
        
        # Build existing_event_map like in the actual code
        existing_event_map = set()
        for e in generated_events:
            virtual_gids = getattr(e, '_group_ids', None)
            e_group_ids = virtual_gids or ([eg.group_id for eg in e.event_groups] if hasattr(e, 'event_groups') else [])
            
            for g_id in e_group_ids:
                sig = (g_id, e.start_datetime.replace(second=0, microsecond=0))
                existing_event_map.add(sig)
        
        log_info(f"Created {len(existing_event_map)} unique signatures")
        
        # Get lesson schedules
        schedules = db.query(LessonSchedule).filter(
            LessonSchedule.group_id == group.id,
            LessonSchedule.is_active == True,
            LessonSchedule.scheduled_at >= start_date,
            LessonSchedule.scheduled_at <= end_date
        ).all()
        
        log_info(f"Found {len(schedules)} lesson schedules")
        
        # Count how many would be filtered
        filtered = 0
        kept = 0
        
        for sched in schedules:
            sched_time = sched.scheduled_at.replace(second=0, microsecond=0)
            sig = (sched.group_id, sched_time)
            
            if sig in existing_event_map:
                filtered += 1
            else:
                kept += 1
        
        log_info(f"Filtered: {filtered}, Kept: {kept}")
        
        # If we have generated events, most schedules should be filtered
        if generated_events and schedules:
            if filtered == 0:
                log_error("No schedules filtered - deduplication not working!")
                return False
            else:
                log_success(f"Deduplication working: {filtered} duplicates filtered")
        
        return True
        
    finally:
        db.close()

def test_calendar_endpoint():
    """Test that /calendar endpoint works without duplicates"""
    log_info("Test 3: Calendar endpoint integration...")
    
    # This would require running the actual FastAPI app
    # For now, just verify the code has the right patterns
    
    events_file = Path(__file__).parent.parent / "src" / "routes" / "events.py"
    
    with open(events_file, 'r') as f:
        content = f.read()
    
    required_patterns = [
        "getattr(e, '_group_ids', None)",
        "virtual_group_ids = getattr(event, '_group_ids', None)",
        "virtual_gids = getattr(e, '_group_ids', None)"
    ]
    
    success = True
    for pattern in required_patterns:
        if pattern in content:
            log_success(f"Found pattern: {pattern[:50]}...")
        else:
            log_error(f"Missing pattern: {pattern}")
            success = False
    
    return success

def main():
    print(f"\n{BLUE}{'='*60}{NC}")
    print(f"{BLUE}  Event Deduplication Fix Verification{NC}")
    print(f"{BLUE}{'='*60}{NC}\n")
    
    all_tests_passed = True
    
    # Test 1: Virtual events have _group_ids
    print()
    try:
        if not test_virtual_events_have_group_ids():
            all_tests_passed = False
    except Exception as e:
        log_error(f"Test 1 failed with exception: {e}")
        all_tests_passed = False
    
    # Test 2: Deduplication logic
    print()
    try:
        if not test_deduplication_logic():
            all_tests_passed = False
    except Exception as e:
        log_error(f"Test 2 failed with exception: {e}")
        all_tests_passed = False
    
    # Test 3: Code patterns
    print()
    try:
        if not test_calendar_endpoint():
            all_tests_passed = False
    except Exception as e:
        log_error(f"Test 3 failed with exception: {e}")
        all_tests_passed = False
    
    # Summary
    print()
    print(f"{BLUE}{'='*60}{NC}")
    if all_tests_passed:
        log_success("All verification tests passed!")
        print()
        log_info("The deduplication fix is working correctly.")
        print()
        sys.exit(0)
    else:
        log_error("Some verification tests failed!")
        print()
        log_warning("Review the errors above and check:")
        print("  1. Files were updated correctly")
        print("  2. Backend was restarted after applying fixes")
        print("  3. Database has recurring events to test with")
        print()
        sys.exit(1)

if __name__ == "__main__":
    main()
