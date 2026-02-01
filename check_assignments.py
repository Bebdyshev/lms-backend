from sqlalchemy import create_session, create_engine
from sqlalchemy.orm import sessionmaker
from src.schemas.models import Assignment, Event
import os

POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://myuser:mypassword@localhost:5432/lms_db")
engine = create_engine(POSTGRES_URL)
Session = sessionmaker(bind=engine)
db = Session()

assignments = db.query(Assignment).order_by(Assignment.id.desc()).limit(5).all()
for a in assignments:
    print(f"ID: {a.id}, Title: {a.title}, Due Date: {a.due_date}, Event ID: {a.event_id}")
    if a.event_id:
        event = db.query(Event).get(a.event_id)
        if event:
            print(f"  Event: {event.title}, Start: {event.start_datetime}")
        else:
            print(f"  Event ID {a.event_id} NOT FOUND in DB")
db.close()
