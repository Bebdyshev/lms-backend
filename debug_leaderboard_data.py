
import sys
import os
from datetime import datetime, timedelta

# Setup path
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

from src.config import SessionLocal
from src.schemas.models import (
    UserInDB, Group, LessonSchedule, Event, Assignment, AssignmentSubmission,
    CourseGroupAccess, EventGroup, EventCourse, Attendance, GroupStudent
)

def debug_leaderboard(group_id, week_number):
    db = SessionLocal()

    print(f"\n==================================================")
    print(f"DEBUGGING LEADERBOARD: Group {group_id}, Week {week_number}")
    print(f"==================================================")

    # 1. Get Group
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        print(f"❌ Group {group_id} not found")
        return
    print(f"✅ Group found: {group.name} (ID: {group.id})")

    # 2. Calculate Date Range
    # Find first schedule ever to establish Week 1
    first_schedule = db.query(LessonSchedule).filter(
        LessonSchedule.group_id == group_id,
        LessonSchedule.is_active == True
    ).order_by(LessonSchedule.scheduled_at).first()
    
    if not first_schedule:
        print("❌ No schedules found to determine start date")
        return

    print(f"\n--- 2. Date Calculation ---")
    print(f"Found first schedule: {first_schedule.scheduled_at.date()}")
    
    # Logic from frontend: start_date is first Monday before/on first schedule
    first_date = first_schedule.scheduled_at
    start_of_week_1 = first_date - timedelta(days=first_date.weekday())
    print(f"Week 1 Start: {start_of_week_1.date()}")
    
    week_start_dt = start_of_week_1 + timedelta(weeks=week_number - 1)
    week_end_dt = week_start_dt + timedelta(days=7)
    
    print(f"Target Week Start: {week_start_dt.date()}")
    print(f"Target Week End:   {week_end_dt.date()}")

    # 3. Fetch Events (Only Lesson Schedules for now, as user implies)
    print(f"\n--- 3. Fetching Events ---")
    
    # 3.4 Lesson Schedules (Pseudo Events)
    schedules = db.query(LessonSchedule).filter(
        LessonSchedule.group_id == group_id,
        LessonSchedule.is_active == True,
        LessonSchedule.scheduled_at >= week_start_dt,
        LessonSchedule.scheduled_at < week_end_dt
    ).order_by(LessonSchedule.scheduled_at).all()
    print(f"Lesson Schedules found: {len(schedules)}")

    events = []
    seen_times = set()

    for sched in schedules:
        time_sig = sched.scheduled_at.replace(second=0, microsecond=0)
        if time_sig not in seen_times:
            lesson_title = sched.lesson.title if sched.lesson else f"Lesson {sched.id}"
            pseudo_event = Event(
                id=sched.id,
                title=lesson_title,
                start_datetime=sched.scheduled_at,
                event_type='class'
            )
            # IMPORTANT: Treating Schedule ID as Event ID for display
            events.append(pseudo_event)
            seen_times.add(time_sig)
    
    events.sort(key=lambda x: x.start_datetime)
    print(f"TOTAL Unique Events for column display: {len(events)}")
    for i, e in enumerate(events):
        print(f"  [{i+1}] {e.start_datetime} - {e.title} (ID: {e.id})")

    # 4. Assignments
    print("\n--- 4. Finding Assignments (STRICT EVENT_ID MATCH) ---")
    
    # Collect all IDs displayed in the schedule
    displayed_event_ids = [e.id for e in events]
    print(f"Searching Assignments for EventIDs: {displayed_event_ids}")
    
    # STRICT QUERY: Only check event_id
    assignments = db.query(Assignment).filter(
        Assignment.event_id.in_(displayed_event_ids),
        Assignment.is_active == True
    ).all()
    
    print(f"Total Assignments found: {len(assignments)}")
    for a in assignments:
        print(f"  - AssignID: {a.id} | Title: {a.title} | EventID: {a.event_id}")

    # Mapping Logic
    event_homework_map = {}
    
    # Only map if event_id matches exactly
    for a in assignments:
        if a.event_id not in event_homework_map:
            event_homework_map[a.event_id] = []
        event_homework_map[a.event_id].append(a)
    
    for e in events:
         if e.id in event_homework_map:
             asns = event_homework_map[e.id]
             for asn in asns:
                 print(f"  -> Schedule/Event {e.id} MATCHES Assignment {asn.id}")
         else:
             print(f"  -> Schedule/Event {e.id} has NO Assignment linked via event_id")

    # 5. Students & Submissions
    print("\n--- 5. Students & Submissions ---")
    students = db.query(UserInDB).join(GroupStudent).filter(
        GroupStudent.group_id == group_id,
        GroupStudent.is_active == True
    ).all()
    student_ids = [s.id for s in students]
    print(f"Student IDs in group: {student_ids}")
    
    assignment_ids = [a.id for a in assignments]
    submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id.in_(assignment_ids),
        AssignmentSubmission.user_id.in_(student_ids)
    ).all()
    print(f"Total Submissions found: {len(submissions)}")
    
    # 6. Attendance
    print("\n--- 6. Attendance ---")
    schedule_ids = displayed_event_ids
    atts = db.query(Attendance).filter(
        Attendance.lesson_schedule_id.in_(schedule_ids),
        Attendance.user_id.in_(student_ids)
    ).all()
    print(f"Schedule Attendance records: {len(atts)}")

    db.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python debug_leaderboard_data.py <group_id> <week_number>")
    else:
        debug_leaderboard(int(sys.argv[1]), int(sys.argv[2]))
