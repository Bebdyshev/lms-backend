from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional


class LeaderboardEntrySchema(BaseModel):
    id: int
    user_id: int
    group_id: int
    week_number: int
    lesson_1: float
    lesson_2: float
    lesson_3: float
    lesson_4: float
    lesson_5: float
    curator_hour: float
    mock_exam: float
    study_buddy: float
    self_reflection_journal: float
    weekly_evaluation: float
    extra_points: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LeaderboardEntryCreateSchema(BaseModel):
    user_id: int
    group_id: int
    week_number: int
    lesson_1: Optional[float] = None
    lesson_2: Optional[float] = None
    lesson_3: Optional[float] = None
    lesson_4: Optional[float] = None
    lesson_5: Optional[float] = None
    curator_hour: Optional[float] = None
    mock_exam: Optional[float] = None
    study_buddy: Optional[float] = None
    self_reflection_journal: Optional[float] = None
    weekly_evaluation: Optional[float] = None
    extra_points: Optional[float] = None


class LeaderboardConfigSchema(BaseModel):
    id: int
    group_id: int
    week_number: int
    curator_hour_enabled: bool
    curator_hour_date: Optional[date] = None
    study_buddy_enabled: bool
    self_reflection_journal_enabled: bool
    weekly_evaluation_enabled: bool
    extra_points_enabled: bool

    class Config:
        from_attributes = True


class LeaderboardConfigUpdateSchema(BaseModel):
    group_id: int
    week_number: int
    curator_hour_enabled: Optional[bool] = None
    curator_hour_date: Optional[date] = None
    study_buddy_enabled: Optional[bool] = None
    self_reflection_journal_enabled: Optional[bool] = None
    weekly_evaluation_enabled: Optional[bool] = None
    extra_points_enabled: Optional[bool] = None


class CuratorRatingSchema(BaseModel):
    id: int
    curator_id: int
    head_curator_id: int
    week_number: int
    professionalism: float
    responsiveness: float
    feedback_quality: float
    retention_rate: float
    extra_points: float
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CuratorRatingCreateSchema(BaseModel):
    curator_id: int
    week_number: int
    professionalism: Optional[float] = 0.0
    responsiveness: Optional[float] = 0.0
    feedback_quality: Optional[float] = 0.0
    retention_rate: Optional[float] = 0.0
    extra_points: Optional[float] = 0.0
    comment: Optional[str] = None
