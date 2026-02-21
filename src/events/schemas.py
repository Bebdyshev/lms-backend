from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List


class EventSchema(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    event_type: str
    start_datetime: datetime
    end_datetime: datetime
    location: Optional[str] = None
    is_online: bool
    meeting_url: Optional[str] = None
    created_by: int
    creator_name: Optional[str] = None
    is_active: bool
    is_recurring: bool
    recurrence_pattern: Optional[str] = None
    recurrence_end_date: Optional[date] = None
    max_participants: Optional[int] = None
    lesson_id: Optional[int] = None
    teacher_id: Optional[int] = None
    teacher_name: Optional[str] = None
    participant_count: int = 0
    groups: Optional[List[str]] = None
    courses: Optional[List[str]] = None
    group_ids: Optional[List[int]] = None
    course_ids: Optional[List[int]] = None
    created_at: datetime
    updated_at: datetime
    is_substitution: bool = False

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z' if v else None
        }


class CreateEventRequest(BaseModel):
    title: str
    description: Optional[str] = None
    event_type: str
    start_datetime: datetime
    end_datetime: datetime
    location: Optional[str] = None
    is_online: bool = True
    meeting_url: Optional[str] = None
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    recurrence_end_date: Optional[date] = None
    max_participants: Optional[int] = None
    teacher_id: Optional[int] = None
    group_ids: List[int] = []
    course_ids: List[int] = []


class UpdateEventRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    event_type: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    location: Optional[str] = None
    is_online: Optional[bool] = None
    meeting_url: Optional[str] = None
    is_active: Optional[bool] = None
    is_recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None
    recurrence_end_date: Optional[date] = None
    max_participants: Optional[int] = None
    teacher_id: Optional[int] = None
    group_ids: Optional[List[int]] = None
    course_ids: Optional[List[int]] = None


class EventGroupSchema(BaseModel):
    id: int
    event_id: int
    group_id: int
    group_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class EventParticipantSchema(BaseModel):
    id: int
    event_id: int
    user_id: int
    user_name: Optional[str] = None
    registration_status: str
    registered_at: datetime
    attended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AttendanceRecord(BaseModel):
    student_id: int
    status: str


class AttendanceBulkUpdateSchema(BaseModel):
    attendance: List[AttendanceRecord]


class EventStudentSchema(BaseModel):
    student_id: int
    name: str
    attendance_status: Optional[str] = "registered"
    last_updated: Optional[datetime] = None


class LessonScheduleSchema(BaseModel):
    id: int
    group_id: int
    lesson_id: int
    scheduled_at: datetime
    week_number: int
    is_active: bool

    class Config:
        from_attributes = True


class AttendanceSchema(BaseModel):
    id: int
    lesson_schedule_id: int
    user_id: int
    status: str
    score: int
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
