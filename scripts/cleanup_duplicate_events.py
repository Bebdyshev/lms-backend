#!/usr/bin/env python3
"""
Script to clean up duplicate Event entries.
This is the ROOT CAUSE of duplicate lessons in the schedule dropdown.
"""

import sys
sys.path.insert(0, '/Users/bebdyshev/Documents/Github/lms/backend')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("POSTGRES_URL")

if not DATABASE_URL:
    print("Error: POSTGRES_URL environment variable not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

def cleanup_duplicate_events():
    print("Finding duplicate Event entries (same group + same start_datetime)...")
    
    # Find duplicate events: same group_id and start_datetime
    duplicates_query = text("""
        WITH event_groups AS (
            SELECT e.id as event_id, eg.group_id, e.start_datetime, e.is_active
            FROM events e
            JOIN event_groups eg ON eg.event_id = e.id
            WHERE e.is_active = true AND e.event_type = 'class'
        ),
        duplicates AS (
            SELECT group_id, start_datetime, COUNT(*) as cnt, ARRAY_AGG(event_id ORDER BY event_id) as event_ids
            FROM event_groups
            GROUP BY group_id, start_datetime
            HAVING COUNT(*) > 1
        )
        SELECT * FROM duplicates ORDER BY group_id, start_datetime
    """)
    
    result = session.execute(duplicates_query)
    duplicates = result.fetchall()
    
    print(f"Found {len(duplicates)} duplicate groups (group + time combinations with multiple events)")
    
    events_to_delete = set()
    
    for row in duplicates:
        group_id, start_datetime, count, event_ids = row
        # Keep the first event ID, mark rest for deletion
        ids_to_delete = event_ids[1:]  # All except first
        events_to_delete.update(ids_to_delete)
        print(f"Group {group_id}, Time {start_datetime}: Keeping event {event_ids[0]}, deleting {ids_to_delete}")
    
    if events_to_delete:
        print(f"\nDeleting {len(events_to_delete)} duplicate events...")
        
        # First delete related event_groups entries
        delete_event_groups = text("DELETE FROM event_groups WHERE event_id = ANY(:ids)")
        session.execute(delete_event_groups, {"ids": list(events_to_delete)})
        
        # Delete related event_courses entries  
        delete_event_courses = text("DELETE FROM event_courses WHERE event_id = ANY(:ids)")
        session.execute(delete_event_courses, {"ids": list(events_to_delete)})
        
        # Delete related event_participants entries
        delete_participants = text("DELETE FROM event_participants WHERE event_id = ANY(:ids)")
        session.execute(delete_participants, {"ids": list(events_to_delete)})
        
        # Finally delete the events
        delete_events = text("DELETE FROM events WHERE id = ANY(:ids)")
        session.execute(delete_events, {"ids": list(events_to_delete)})
        
        session.commit()
        print(f"Deleted {len(events_to_delete)} duplicate events!")
    else:
        print("No duplicates to delete.")
    
    # Verify
    verify_query = text("""
        SELECT COUNT(*) FROM (
            WITH event_groups AS (
                SELECT e.id as event_id, eg.group_id, e.start_datetime
                FROM events e
                JOIN event_groups eg ON eg.event_id = e.id
                WHERE e.is_active = true AND e.event_type = 'class'
            )
            SELECT group_id, start_datetime
            FROM event_groups
            GROUP BY group_id, start_datetime
            HAVING COUNT(*) > 1
        ) as dups
    """)
    remaining = session.execute(verify_query).scalar()
    print(f"\nRemaining duplicate groups: {remaining}")

if __name__ == "__main__":
    try:
        cleanup_duplicate_events()
        print("\nCleanup completed successfully!")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()
