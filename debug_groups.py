from src.config import SessionLocal
from src.schemas.models import UserInDB, Group, GroupStudent, Event, EventGroup
from datetime import datetime, timedelta

def debug_group(group_id):
    db = SessionLocal()
    try:
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            print(f"Group {group_id} not found")
            return

        print(f"Group: {group.name} (ID: {group.id})")
        print(f"Teacher ID: {group.teacher_id}")
        teacher = db.query(UserInDB).filter(UserInDB.id == group.teacher_id).first()
        print(f"Teacher: {teacher.name if teacher else 'None'}")

        students = db.query(GroupStudent).filter(GroupStudent.group_id == group_id).all()
        print(f"Students count: {len(students)}")
        for gs in students:
            s = db.query(UserInDB).filter(UserInDB.id == gs.student_id).first()
            print(f" - {s.name if s else 'Unknown'} (ID: {gs.student_id})")

        # Direct Class Events
        events = db.query(Event).join(EventGroup).filter(
            EventGroup.group_id == group_id,
            Event.event_type == 'class',
            Event.is_active == True
        ).all()
        print(f"Direct class events count: {len(events)}")
        for e in events:
            print(f" - {e.title} at {e.start_datetime} (Recurring: {e.is_recurring})")

        # Recurring check
        recurring = db.query(Event).join(EventGroup).filter(
            EventGroup.group_id == group_id,
            Event.is_recurring == True,
            Event.is_active == True
        ).all()
        print(f"Recurring events: {len(recurring)}")

    finally:
        db.close()

if __name__ == "__main__":
    import sys
    gid = 4 # Teacher - Intensive 1 from screenshot seems to be a group, let's find its ID or just list groups
    # Let's list all groups first to find the right one
    db = SessionLocal()
    groups = db.query(Group).all()
    for g in groups:
        print(f"ID: {g.id} | Name: {g.name}")
    db.close()
    
    if len(sys.argv) > 1:
        debug_group(int(sys.argv[1]))
