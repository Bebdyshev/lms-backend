#!/usr/bin/env python3
"""
Script to clean up duplicate LessonSchedule entries.
Run this before applying the unique constraint migration.
"""

import sys
sys.path.insert(0, '/Users/bebdyshev/Documents/Github/lms/backend')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Database URL from environment
DATABASE_URL = os.getenv("POSTGRES_URL")

if not DATABASE_URL:
    print("Error: POSTGRES_URL environment variable not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

def cleanup_duplicates():
    print("Finding duplicate LessonSchedule entries...")
    
    # Find duplicates: same group_id and scheduled_at
    duplicates_query = text("""
        SELECT group_id, scheduled_at, COUNT(*) as cnt, ARRAY_AGG(id ORDER BY id) as ids
        FROM lesson_schedules
        WHERE is_active = true
        GROUP BY group_id, scheduled_at
        HAVING COUNT(*) > 1
    """)
    
    result = session.execute(duplicates_query)
    duplicates = result.fetchall()
    
    total_removed = 0
    
    for row in duplicates:
        group_id, scheduled_at, count, ids = row
        # Keep the first ID, delete the rest
        ids_to_delete = ids[1:]  # All except first
        
        print(f"Group {group_id}, Time {scheduled_at}: Found {count} entries, removing {len(ids_to_delete)} duplicates")
        
        if ids_to_delete:
            delete_query = text("DELETE FROM lesson_schedules WHERE id = ANY(:ids)")
            session.execute(delete_query, {"ids": ids_to_delete})
            total_removed += len(ids_to_delete)
    
    session.commit()
    print(f"\nTotal duplicates removed: {total_removed}")
    
    # Verify
    verify_query = text("""
        SELECT COUNT(*) FROM (
            SELECT group_id, scheduled_at
            FROM lesson_schedules
            WHERE is_active = true
            GROUP BY group_id, scheduled_at
            HAVING COUNT(*) > 1
        ) as dups
    """)
    remaining = session.execute(verify_query).scalar()
    print(f"Remaining duplicate groups: {remaining}")

if __name__ == "__main__":
    try:
        cleanup_duplicates()
        print("\nCleanup completed successfully!")
    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
    finally:
        session.close()
