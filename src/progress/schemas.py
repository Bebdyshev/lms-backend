from pydantic import BaseModel, field_validator
from datetime import datetime, date
from typing import Optional


class StepProgressSchema(BaseModel):
    id: int
    user_id: int
    course_id: int
    lesson_id: int
    step_id: int
    status: str
    started_at: Optional[datetime] = None
    visited_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    time_spent_minutes: int

    class Config:
        from_attributes = True


class StepProgressCreateSchema(BaseModel):
    step_id: int
    time_spent_minutes: int = 0


class ProgressSnapshotSchema(BaseModel):
    id: int
    user_id: int
    course_id: Optional[int] = None
    snapshot_date: date
    completed_steps: int
    total_steps: int
    completion_percentage: float
    total_time_spent_minutes: int
    assignments_completed: int
    total_assignments: int
    assignment_score_percentage: float
    created_at: datetime

    class Config:
        from_attributes = True


class QuizAttemptSchema(BaseModel):
    id: int
    user_id: int
    step_id: int
    course_id: int
    lesson_id: int
    quiz_title: Optional[str] = None
    total_questions: int
    correct_answers: int
    score_percentage: float
    answers: Optional[str] = None
    time_spent_seconds: Optional[int] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_draft: bool = False
    current_question_index: Optional[int] = None
    quiz_content_hash: Optional[str] = None
    is_graded: Optional[bool] = True
    feedback: Optional[str] = None
    graded_by: Optional[int] = None
    graded_at: Optional[datetime] = None

    @field_validator('is_graded', mode='before')
    @classmethod
    def default_is_graded(cls, v):
        return v if v is not None else True

    class Config:
        from_attributes = True


class QuizAttemptCreateSchema(BaseModel):
    step_id: int
    course_id: int
    lesson_id: int
    quiz_title: Optional[str] = None
    total_questions: int
    correct_answers: int = 0
    score_percentage: float = 0
    answers: Optional[str] = None
    time_spent_seconds: Optional[int] = None
    is_graded: bool = True
    is_draft: bool = False
    current_question_index: Optional[int] = None
    quiz_content_hash: Optional[str] = None


class QuizAttemptUpdateSchema(BaseModel):
    answers: Optional[str] = None
    current_question_index: Optional[int] = None
    time_spent_seconds: Optional[int] = None
    is_draft: Optional[bool] = None
    correct_answers: Optional[int] = None
    score_percentage: Optional[float] = None
    is_graded: Optional[bool] = None
    total_questions: Optional[int] = None


class QuizAttemptGradeSchema(BaseModel):
    score_percentage: float
    correct_answers: int
    feedback: Optional[str] = None


class ProgressSchema(BaseModel):
    id: int
    user_id: int
    course_id: int
    lesson_id: Optional[int] = None
    assignment_id: Optional[int] = None
    status: str
    completion_percentage: int
    time_spent_minutes: int
    last_accessed: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StudentCourseSummarySchema(BaseModel):
    id: int
    user_id: int
    course_id: int
    total_steps: int
    completed_steps: int
    completion_percentage: float
    total_time_spent_minutes: int
    total_assignments: int
    completed_assignments: int
    average_assignment_percentage: float
    last_activity_at: Optional[datetime] = None
    last_lesson_title: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class CourseAnalyticsCacheSchema(BaseModel):
    id: int
    course_id: int
    total_enrolled: int
    active_students_7d: int
    active_students_30d: int
    average_completion_percentage: float
    average_assignment_score: float
    total_modules: int
    total_lessons: int
    total_steps: int
    total_assignments: int
    last_calculated_at: datetime

    class Config:
        from_attributes = True
