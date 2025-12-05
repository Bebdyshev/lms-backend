
import sys
import os

# Add the parent directory to sys.path to allow importing from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import SessionLocal
from src.schemas.models import Event, EventGroup, EventParticipant

def delete_all_events():
    db = SessionLocal()
    try:
        print("Deleting all events and related data...")
        
        # Delete related data first
        print("Deleting event participants...")
        db.query(EventParticipant).delete()
        
        print("Deleting event groups...")
        db.query(EventGroup).delete()
        
        print("Deleting events...")
        deleted_count = db.query(Event).delete()
        
        db.commit()
        print(f"Successfully deleted {deleted_count} events and all related data.")
    except Exception as e:
        print(f"Error deleting events: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    delete_all_events()
