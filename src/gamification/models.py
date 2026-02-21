from sqlalchemy import Column, String, Integer, Float, DateTime, Date, Boolean, ForeignKey, Text, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from src.models.base import Base


class LeaderboardEntry(Base):
    __tablename__ = "leaderboard_entries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    week_number = Column(Integer, nullable=False)
    lesson_1 = Column(Float, default=0.0)
    lesson_2 = Column(Float, default=0.0)
    lesson_3 = Column(Float, default=0.0)
    lesson_4 = Column(Float, default=0.0)
    lesson_5 = Column(Float, default=0.0)
    curator_hour = Column(Float, default=0.0)
    mock_exam = Column(Float, default=0.0)
    study_buddy = Column(Float, default=0.0)
    self_reflection_journal = Column(Float, default=0.0)
    weekly_evaluation = Column(Float, default=0.0)
    extra_points = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("UserInDB", foreign_keys=[user_id])
    group = relationship("Group", foreign_keys=[group_id])

    __table_args__ = (
        UniqueConstraint('user_id', 'group_id', 'week_number', name='uq_leaderboard_entry'),
    )


class LeaderboardConfig(Base):
    __tablename__ = "leaderboard_configs"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    week_number = Column(Integer, nullable=False)
    curator_hour_enabled = Column(Boolean, default=True)
    curator_hour_date = Column(Date, nullable=True)
    study_buddy_enabled = Column(Boolean, default=True)
    self_reflection_journal_enabled = Column(Boolean, default=True)
    weekly_evaluation_enabled = Column(Boolean, default=True)
    extra_points_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    group = relationship("Group", foreign_keys=[group_id])
    __table_args__ = (
        UniqueConstraint('group_id', 'week_number', name='uq_leaderboard_config'),
    )


class CuratorRating(Base):
    """Head Curator's manual evaluation of other curators."""
    __tablename__ = "curator_ratings"
    id = Column(Integer, primary_key=True, index=True)
    curator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    head_curator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    week_number = Column(Integer, nullable=False)
    professionalism = Column(Float, default=0.0)
    responsiveness = Column(Float, default=0.0)
    feedback_quality = Column(Float, default=0.0)
    retention_rate = Column(Float, default=0.0)
    extra_points = Column(Float, default=0.0)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    curator = relationship("UserInDB", foreign_keys=[curator_id])
    head_curator = relationship("UserInDB", foreign_keys=[head_curator_id])

    __table_args__ = (
        UniqueConstraint('curator_id', 'week_number', name='uq_curator_rating_week'),
    )


class DailyQuestionCompletion(Base):
    """Tracks when a student completes their daily recommended questions."""
    __tablename__ = "daily_question_completions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    completed_date = Column(Date, nullable=False, index=True)
    questions_data = Column(JSON, nullable=True)
    score = Column(Integer, nullable=True)
    total_questions = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("UserInDB", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint('user_id', 'completed_date', name='uq_daily_question_user_date'),
    )
