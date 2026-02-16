from sqlalchemy import (
    Column, String, Integer, BigInteger, Float, DateTime, Date, Time, ForeignKey, Text, Enum, ARRAY, Boolean, UniqueConstraint, JSON, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, date, time, timezone
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Union, Dict
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
import json

Base = declarative_base()

# =============================================================================
# QUIZ MODELS
# =============================================================================

class QuestionOption(BaseModel):
    id: str
    text: str
    is_correct: bool = False

class MatchingPair(BaseModel):
    left: str
    right: str

class QuizQuestion(BaseModel):
    id: str
    assignment_id: str = ""
    question_text: str
    question_type: str  # single_choice, multiple_choice, fill_blank, long_text, media_question, matching
    options: Optional[List[QuestionOption]] = None
    correct_answer: Union[str, List[str]] = ""
    points: int = 1
    order_index: int = 0
    # New fields for enhanced question types
    media_url: Optional[str] = None  # For PDF/image attachments
    media_type: Optional[str] = None  # 'pdf', 'image'
    expected_length: Optional[int] = None  # For long text questions (character count)
    keywords: Optional[List[str]] = None  # For auto-grading long text answers
    # Matching question fields
    matching_pairs: Optional[List[MatchingPair]] = None  # Pairs for matching questions

class QuizData(BaseModel):
    title: str
    questions: List[QuizQuestion]
    time_limit_minutes: Optional[int] = None
    max_score: Optional[int] = None

# =============================================================================
# MULTI-TASK ASSIGNMENT MODELS
# =============================================================================

class TaskItem(BaseModel):
    """Individual task within a multi-task assignment"""
    id: str  # Unique ID for this task
    task_type: str  # 'course_unit', 'file_task', 'text_task', 'link_task', 'pdf_text_task'
    title: str
    description: Optional[str] = None
    order_index: int
    points: int = 10
    content: dict  # Task-specific content based on task_type
    
    # Task type specific fields (stored in content dict):
    # course_unit: { course_id: int, lesson_ids: List[int] }
    # file_task: { question: str, allowed_file_types: List[str], max_file_size_mb: int, teacher_file_url: str, teacher_file_name: str }
    # text_task: { question: str, max_length: int, keywords: List[str] }
    # link_task: { url: str, link_description: str, completion_criteria: str }
    # pdf_text_task: { question: str, max_length: int, keywords: List[str], teacher_file_url: str, teacher_file_name: str }

class MultiTaskContent(BaseModel):
    """Content structure for multi-task assignments"""
    tasks: List[TaskItem]
    total_points: int
    instructions: Optional[str] = None  # Overall instructions for the assignment

# =============================================================================
# FLASHCARD MODELS
# =============================================================================

class FlashcardItem(BaseModel):
    id: str
    front_text: str
    back_text: str
    front_image_url: Optional[str] = None
    back_image_url: Optional[str] = None
    difficulty: str = "normal"  # easy, normal, hard
    tags: Optional[List[str]] = None
    order_index: int = 0

class FlashcardSet(BaseModel):
    title: str
    description: Optional[str] = None
    cards: List[FlashcardItem]
    study_mode: str = "sequential"  # sequential, random, spaced_repetition
    auto_flip: bool = False
    show_progress: bool = True

# =============================================================================
# FAVORITE FLASHCARD MODELS
# =============================================================================

class FavoriteFlashcard(Base):
    __tablename__ = "favorite_flashcards"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(Integer, ForeignKey("steps.id", ondelete="CASCADE"), nullable=True)
    flashcard_id = Column(String, nullable=False)  # ID карточки внутри flashcard set
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=True)
    flashcard_data = Column(Text, nullable=False)  # JSON данные самой карточки
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("UserInDB", back_populates="favorite_flashcards")
    step = relationship("Step", back_populates="favorite_flashcards")
    
    # Unique constraint - один студент не может добавить одну и ту же карточку дважды
    __table_args__ = (
        UniqueConstraint('user_id', 'step_id', 'flashcard_id', name='uq_user_flashcard'),
    )

class FavoriteFlashcardSchema(BaseModel):
    id: int
    user_id: int
    step_id: Optional[int] = None
    flashcard_id: str
    lesson_id: Optional[int] = None
    course_id: Optional[int] = None
    flashcard_data: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class FavoriteFlashcardCreateSchema(BaseModel):
    step_id: Optional[int] = None
    flashcard_id: str
    lesson_id: Optional[int] = None
    course_id: Optional[int] = None
    flashcard_data: str  # JSON string with FlashcardItem data

# =============================================================================
# ASSIGNMENT ZERO MODELS - Self-Assessment Questionnaire for New Students
# =============================================================================

class AssignmentZeroSubmission(Base):
    """Stores self-assessment questionnaire data for new students"""
    __tablename__ = "assignment_zero_submissions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Personal Information
    full_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    parent_phone_number = Column(String, nullable=False)
    telegram_id = Column(String, nullable=False)
    email = Column(String, nullable=False)  # Email for weekly tests
    college_board_email = Column(String, nullable=False)
    college_board_password = Column(String, nullable=False)
    birthday_date = Column(Date, nullable=False)
    city = Column(String, nullable=False)
    
    # School Information
    school_type = Column(String, nullable=False)  # NIS, RFMS, BIL, Private, Public
    group_name = Column(String, nullable=False)
    
    # SAT Information
    sat_target_date = Column(String, nullable=False)  # October, November, December, March, May
    has_passed_sat_before = Column(Boolean, default=False)
    previous_sat_score = Column(String, nullable=True)  # e.g., "October 2024 - Math 650, Verbal 550"
    recent_practice_test_score = Column(String, nullable=False)  # Description of recent practice
    bluebook_practice_test_5_score = Column(String, nullable=False)  # e.g., "Math 500, Verbal 560"
    
    # File Upload
    screenshot_url = Column(String, nullable=True)  # URL to uploaded screenshot
    
    # Grammar Assessment (1-5 scale: 1=Don't know, 5=Mastered)
    grammar_punctuation = Column(Integer, nullable=True)  # Punctuation
    grammar_noun_clauses = Column(Integer, nullable=True)  # Noun Clauses
    grammar_relative_clauses = Column(Integer, nullable=True)  # Relative Clauses
    grammar_verb_forms = Column(Integer, nullable=True)  # Verb Forms and Tenses
    grammar_comparisons = Column(Integer, nullable=True)  # Comparisons
    grammar_transitions = Column(Integer, nullable=True)  # Transitions
    grammar_synthesis = Column(Integer, nullable=True)  # Synthesis Questions
    
    # Reading Skills Assessment (1-5 scale)
    reading_word_in_context = Column(Integer, nullable=True)  # Words in Context
    reading_text_structure = Column(Integer, nullable=True)  # Text Structure and Purpose
    reading_cross_text = Column(Integer, nullable=True)  # Cross-Text Connections
    reading_central_ideas = Column(Integer, nullable=True)  # Central Ideas and Details
    reading_inferences = Column(Integer, nullable=True)  # Inferences
    
    # SAT Passage Types Assessment (1-5 scale)
    passages_literary = Column(Integer, nullable=True)  # Literary passages
    passages_social_science = Column(Integer, nullable=True)  # Social science passages
    passages_humanities = Column(Integer, nullable=True)  # Humanities passages
    passages_science = Column(Integer, nullable=True)  # Science passages
    passages_poetry = Column(Integer, nullable=True)  # Poetry passages
    
    # Math Topics (JSON array of selected topics)
    math_topics = Column(JSON, nullable=True)  # List of selected topics
    
    # =============================================================================
    # IELTS Specific Fields (shown when user belongs to IELTS group)
    # =============================================================================
    
    # IELTS Test Information
    ielts_target_date = Column(String, nullable=True)  # Target IELTS test date
    has_passed_ielts_before = Column(Boolean, default=False)
    previous_ielts_score = Column(String, nullable=True)  # e.g., "Overall 6.5 - L:7 R:6.5 W:6 S:6.5"
    ielts_target_score = Column(String, nullable=True)  # Target overall band score
    
    # IELTS Listening Assessment (1-5 scale)
    ielts_listening_main_idea = Column(Integer, nullable=True)  # Understanding main ideas
    ielts_listening_details = Column(Integer, nullable=True)  # Catching specific details
    ielts_listening_opinion = Column(Integer, nullable=True)  # Understanding opinions/attitudes
    ielts_listening_accents = Column(Integer, nullable=True)  # Understanding different accents
    
    # IELTS Reading Assessment (1-5 scale)
    ielts_reading_skimming = Column(Integer, nullable=True)  # Skimming for main ideas
    ielts_reading_scanning = Column(Integer, nullable=True)  # Scanning for specific info
    ielts_reading_vocabulary = Column(Integer, nullable=True)  # Academic vocabulary
    ielts_reading_inference = Column(Integer, nullable=True)  # Making inferences
    ielts_reading_matching = Column(Integer, nullable=True)  # Matching headings/info
    
    # IELTS Writing Assessment (1-5 scale)
    ielts_writing_task1_graphs = Column(Integer, nullable=True)  # Describing graphs/charts
    ielts_writing_task1_process = Column(Integer, nullable=True)  # Describing processes
    ielts_writing_task2_structure = Column(Integer, nullable=True)  # Essay structure
    ielts_writing_task2_arguments = Column(Integer, nullable=True)  # Developing arguments
    ielts_writing_grammar = Column(Integer, nullable=True)  # Grammar accuracy
    ielts_writing_vocabulary = Column(Integer, nullable=True)  # Vocabulary range
    
    # IELTS Speaking Assessment (1-5 scale)
    ielts_speaking_fluency = Column(Integer, nullable=True)  # Fluency and coherence
    ielts_speaking_vocabulary = Column(Integer, nullable=True)  # Lexical resource
    ielts_speaking_grammar = Column(Integer, nullable=True)  # Grammatical range
    ielts_speaking_pronunciation = Column(Integer, nullable=True)  # Pronunciation
    ielts_speaking_part2 = Column(Integer, nullable=True)  # Long turn speaking (Part 2)
    ielts_speaking_part3 = Column(Integer, nullable=True)  # Discussion skills (Part 3)
    
    # IELTS Topics (JSON array of topics that need improvement)
    ielts_weak_topics = Column(JSON, nullable=True)  # List of weak areas
    
    # Additional comments
    additional_comments = Column(Text, nullable=True)
    
    # Progress tracking for auto-save
    is_draft = Column(Boolean, default=True)  # True = in progress, False = submitted
    last_saved_step = Column(Integer, default=1)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationship
    user = relationship("UserInDB", backref="assignment_zero_submission")

class AssignmentZeroSubmissionSchema(BaseModel):
    id: int
    user_id: int
    full_name: str
    phone_number: str
    parent_phone_number: str
    telegram_id: str
    email: str
    college_board_email: str
    college_board_password: str
    birthday_date: date
    city: str
    school_type: str
    group_name: str
    sat_target_date: str
    has_passed_sat_before: bool
    previous_sat_score: Optional[str] = None
    recent_practice_test_score: str
    bluebook_practice_test_5_score: str
    screenshot_url: Optional[str] = None
    
    # Grammar Assessment (1-5 scale)
    grammar_punctuation: Optional[int] = None
    grammar_noun_clauses: Optional[int] = None
    grammar_relative_clauses: Optional[int] = None
    grammar_verb_forms: Optional[int] = None
    grammar_comparisons: Optional[int] = None
    grammar_transitions: Optional[int] = None
    grammar_synthesis: Optional[int] = None
    
    # Reading Skills Assessment (1-5 scale)
    reading_word_in_context: Optional[int] = None
    reading_text_structure: Optional[int] = None
    reading_cross_text: Optional[int] = None
    reading_central_ideas: Optional[int] = None
    reading_inferences: Optional[int] = None
    
    # SAT Passage Types Assessment (1-5 scale)
    passages_literary: Optional[int] = None
    passages_social_science: Optional[int] = None
    passages_humanities: Optional[int] = None
    passages_science: Optional[int] = None
    passages_poetry: Optional[int] = None
    
    # Math Topics
    math_topics: Optional[List[str]] = None
    
    # IELTS Fields
    ielts_target_date: Optional[str] = None
    has_passed_ielts_before: Optional[bool] = False
    previous_ielts_score: Optional[str] = None
    ielts_target_score: Optional[str] = None
    
    # IELTS Listening Assessment
    ielts_listening_main_idea: Optional[int] = None
    ielts_listening_details: Optional[int] = None
    ielts_listening_opinion: Optional[int] = None
    ielts_listening_accents: Optional[int] = None
    
    # IELTS Reading Assessment
    ielts_reading_skimming: Optional[int] = None
    ielts_reading_scanning: Optional[int] = None
    ielts_reading_vocabulary: Optional[int] = None
    ielts_reading_inference: Optional[int] = None
    ielts_reading_matching: Optional[int] = None
    
    # IELTS Writing Assessment
    ielts_writing_task1_graphs: Optional[int] = None
    ielts_writing_task1_process: Optional[int] = None
    ielts_writing_task2_structure: Optional[int] = None
    ielts_writing_task2_arguments: Optional[int] = None
    ielts_writing_grammar: Optional[int] = None
    ielts_writing_vocabulary: Optional[int] = None
    
    # IELTS Speaking Assessment
    ielts_speaking_fluency: Optional[int] = None
    ielts_speaking_vocabulary: Optional[int] = None
    ielts_speaking_grammar: Optional[int] = None
    ielts_speaking_pronunciation: Optional[int] = None
    ielts_speaking_part2: Optional[int] = None
    ielts_speaking_part3: Optional[int] = None
    
    # IELTS Weak Topics
    ielts_weak_topics: Optional[List[str]] = None
    
    # Additional comments
    additional_comments: Optional[str] = None
    
    # Progress tracking
    is_draft: bool = False
    last_saved_step: int = 1
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class AssignmentZeroSubmitSchema(BaseModel):
    full_name: str
    phone_number: str
    parent_phone_number: str
    telegram_id: str
    email: str
    college_board_email: str
    college_board_password: str
    birthday_date: date
    city: str
    school_type: str
    group_name: str
    sat_target_date: str
    has_passed_sat_before: bool = False
    previous_sat_score: Optional[str] = None
    recent_practice_test_score: str
    bluebook_practice_test_5_score: str
    screenshot_url: Optional[str] = None
    
    # Grammar Assessment (1-5 scale)
    grammar_punctuation: Optional[int] = None
    grammar_noun_clauses: Optional[int] = None
    grammar_relative_clauses: Optional[int] = None
    grammar_verb_forms: Optional[int] = None
    grammar_comparisons: Optional[int] = None
    grammar_transitions: Optional[int] = None
    grammar_synthesis: Optional[int] = None
    
    # Reading Skills Assessment (1-5 scale)
    reading_word_in_context: Optional[int] = None
    reading_text_structure: Optional[int] = None
    reading_cross_text: Optional[int] = None
    reading_central_ideas: Optional[int] = None
    reading_inferences: Optional[int] = None
    
    # SAT Passage Types Assessment (1-5 scale)
    passages_literary: Optional[int] = None
    passages_social_science: Optional[int] = None
    passages_humanities: Optional[int] = None
    passages_science: Optional[int] = None
    passages_poetry: Optional[int] = None
    
    # Math Topics
    math_topics: Optional[List[str]] = None
    
    # IELTS Fields
    ielts_target_date: Optional[str] = None
    has_passed_ielts_before: Optional[bool] = False
    previous_ielts_score: Optional[str] = None
    ielts_target_score: Optional[str] = None
    
    # IELTS Listening Assessment
    ielts_listening_main_idea: Optional[int] = None
    ielts_listening_details: Optional[int] = None
    ielts_listening_opinion: Optional[int] = None
    ielts_listening_accents: Optional[int] = None
    
    # IELTS Reading Assessment
    ielts_reading_skimming: Optional[int] = None
    ielts_reading_scanning: Optional[int] = None
    ielts_reading_vocabulary: Optional[int] = None
    ielts_reading_inference: Optional[int] = None
    ielts_reading_matching: Optional[int] = None
    
    # IELTS Writing Assessment
    ielts_writing_task1_graphs: Optional[int] = None
    ielts_writing_task1_process: Optional[int] = None
    ielts_writing_task2_structure: Optional[int] = None
    ielts_writing_task2_arguments: Optional[int] = None
    ielts_writing_grammar: Optional[int] = None
    ielts_writing_vocabulary: Optional[int] = None
    
    # IELTS Speaking Assessment
    ielts_speaking_fluency: Optional[int] = None
    ielts_speaking_vocabulary: Optional[int] = None
    ielts_speaking_grammar: Optional[int] = None
    ielts_speaking_pronunciation: Optional[int] = None
    ielts_speaking_part2: Optional[int] = None
    ielts_speaking_part3: Optional[int] = None
    
    # IELTS Weak Topics
    ielts_weak_topics: Optional[List[str]] = None
    
    # Additional comments
    additional_comments: Optional[str] = None

# Schema for saving progress (partial data)
class AssignmentZeroSaveProgressSchema(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    parent_phone_number: Optional[str] = None
    telegram_id: Optional[str] = None
    email: Optional[str] = None
    college_board_email: Optional[str] = None
    college_board_password: Optional[str] = None
    birthday_date: Optional[date] = None
    city: Optional[str] = None
    school_type: Optional[str] = None
    group_name: Optional[str] = None
    sat_target_date: Optional[str] = None
    has_passed_sat_before: Optional[bool] = None
    previous_sat_score: Optional[str] = None
    recent_practice_test_score: Optional[str] = None
    bluebook_practice_test_5_score: Optional[str] = None
    screenshot_url: Optional[str] = None
    
    # Grammar Assessment
    grammar_punctuation: Optional[int] = None
    grammar_noun_clauses: Optional[int] = None
    grammar_relative_clauses: Optional[int] = None
    grammar_verb_forms: Optional[int] = None
    grammar_comparisons: Optional[int] = None
    grammar_transitions: Optional[int] = None
    grammar_synthesis: Optional[int] = None
    
    # Reading Skills Assessment
    reading_word_in_context: Optional[int] = None
    reading_text_structure: Optional[int] = None
    reading_cross_text: Optional[int] = None
    reading_central_ideas: Optional[int] = None
    reading_inferences: Optional[int] = None
    
    # SAT Passage Types Assessment
    passages_literary: Optional[int] = None
    passages_social_science: Optional[int] = None
    passages_humanities: Optional[int] = None
    passages_science: Optional[int] = None
    passages_poetry: Optional[int] = None
    
    # Math Topics
    math_topics: Optional[List[str]] = None
    
    # IELTS Fields
    ielts_target_date: Optional[str] = None
    has_passed_ielts_before: Optional[bool] = None
    previous_ielts_score: Optional[str] = None
    ielts_target_score: Optional[str] = None
    
    # IELTS Listening Assessment
    ielts_listening_main_idea: Optional[int] = None
    ielts_listening_details: Optional[int] = None
    ielts_listening_opinion: Optional[int] = None
    ielts_listening_accents: Optional[int] = None
    
    # IELTS Reading Assessment
    ielts_reading_skimming: Optional[int] = None
    ielts_reading_scanning: Optional[int] = None
    ielts_reading_vocabulary: Optional[int] = None
    ielts_reading_inference: Optional[int] = None
    ielts_reading_matching: Optional[int] = None
    
    # IELTS Writing Assessment
    ielts_writing_task1_graphs: Optional[int] = None
    ielts_writing_task1_process: Optional[int] = None
    ielts_writing_task2_structure: Optional[int] = None
    ielts_writing_task2_arguments: Optional[int] = None
    ielts_writing_grammar: Optional[int] = None
    ielts_writing_vocabulary: Optional[int] = None
    
    # IELTS Speaking Assessment
    ielts_speaking_fluency: Optional[int] = None
    ielts_speaking_vocabulary: Optional[int] = None
    ielts_speaking_grammar: Optional[int] = None
    ielts_speaking_pronunciation: Optional[int] = None
    ielts_speaking_part2: Optional[int] = None
    ielts_speaking_part3: Optional[int] = None
    
    # IELTS Weak Topics
    ielts_weak_topics: Optional[List[str]] = None
    
    # Additional comments
    additional_comments: Optional[str] = None
    
    # Progress tracking
    last_saved_step: Optional[int] = None

# =============================================================================
# USER MODELS - LMS PLATFORM
# =============================================================================

class UserInDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="student")  # student, teacher, head_curator, curator, admin
    avatar_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    refresh_token = Column(String, nullable=True)
    
    # Push notifications
    push_token = Column(String, nullable=True, index=True)
    device_type = Column(String, nullable=True)  # 'expo', 'ios', 'android'
    
    # Onboarding tracking
    onboarding_completed = Column(Boolean, default=False, nullable=False)
    onboarding_completed_at = Column(DateTime, nullable=True)
    
    # Assignment Zero (self-assessment questionnaire for new students)
    assignment_zero_completed = Column(Boolean, default=False, nullable=False)
    assignment_zero_completed_at = Column(DateTime, nullable=True)
    
    # Student specific fields
    student_id = Column(String, unique=True, nullable=True)  # For students only
    total_study_time_minutes = Column(Integer, default=0, nullable=False)
    daily_streak = Column(Integer, default=0, nullable=False)  # Current daily streak count
    last_activity_date = Column(Date, nullable=True)  # Last date when student was active
    activity_points = Column(BigInteger, default=0, nullable=False)  # Gamification: total XP points
    
    # Teacher preferences
    no_substitutions = Column(Boolean, default=False, nullable=False)  # Opt-out of substitution requests
    
    # Relationships
    groups = relationship("GroupStudent", back_populates="student", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="user", cascade="all, delete-orphan")
    progress_records = relationship("StudentProgress", back_populates="user", cascade="all, delete-orphan")
    sent_messages = relationship("Message", foreign_keys="Message.from_user_id", back_populates="sender", cascade="all, delete-orphan")
    received_messages = relationship("Message", foreign_keys="Message.to_user_id", back_populates="recipient", cascade="all, delete-orphan")
    created_courses = relationship("Course", back_populates="teacher")
    assignment_submissions = relationship("AssignmentSubmission", foreign_keys="AssignmentSubmission.user_id", back_populates="user", cascade="all, delete-orphan")
    favorite_flashcards = relationship("FavoriteFlashcard", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    step_progress = relationship("StepProgress", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    point_history = relationship("PointHistory", back_populates="user", cascade="all, delete-orphan")
    # Head Teacher: courses managed by this user
    managed_courses = relationship("Course", secondary="course_head_teachers", back_populates="head_teachers")
    
    @property
    def course_ids(self) -> List[int]:
        return [c.id for c in self.managed_courses] if self.managed_courses else []

# =============================================================================
# POINT HISTORY MODEL - Gamification
# =============================================================================

class PointHistory(Base):
    """Tracks every point transaction for leaderboard calculations."""
    __tablename__ = "point_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # Can be positive or negative
    reason = Column(String, nullable=False)  # 'homework', 'quiz', 'teacher_bonus', 'streak_bonus', 'flashcard_review'
    description = Column(String, nullable=True)  # Optional details
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    # Relationship
    user = relationship("UserInDB", back_populates="point_history")
    
    # Index for efficient monthly queries
    __table_args__ = (
        Index('ix_point_history_user_created', 'user_id', 'created_at'),
    )

class PointHistorySchema(BaseModel):
    id: int
    user_id: int
    amount: int
    reason: str
    description: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    refresh_token: str
    type: str

class UserSchema(BaseModel):
    id: int
    email: str
    name: str
    role: str
    avatar_url: Optional[str] = None
    is_active: bool
    student_id: Optional[str] = None
    teacher_name: Optional[str] = None
    curator_name: Optional[str] = None
    group_ids: Optional[List[int]] = None  # List of group IDs for students
    total_study_time_minutes: Optional[int] = 0
    daily_streak: Optional[int] = 0
    last_activity_date: Optional[date] = None
    onboarding_completed: Optional[bool] = False
    onboarding_completed_at: Optional[datetime] = None
    assignment_zero_completed: Optional[bool] = False
    assignment_zero_completed_at: Optional[datetime] = None
    activity_points: Optional[int] = 0
    no_substitutions: Optional[bool] = False
    course_ids: Optional[List[int]] = []  # List of course IDs for head teachers
    created_at: datetime

    class Config:
        from_attributes = True

# =============================================================================
# GROUP MODELS
# =============================================================================

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    curator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    schedule_config = Column(JSONB, nullable=True)

    # Relationships
    teacher = relationship("UserInDB", foreign_keys=[teacher_id], post_update=True)
    curator = relationship("UserInDB", foreign_keys=[curator_id], post_update=True)
    students = relationship("GroupStudent", back_populates="group", cascade="all, delete-orphan")

class GroupSchema(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    teacher_id: int
    teacher_name: Optional[str] = None
    curator_id: Optional[int] = None
    curator_name: Optional[str] = None
    student_count: int = 0
    students: Optional[List["UserSchema"]] = None
    created_at: datetime
    is_active: bool
    schedule_config: Optional[dict] = None
    current_week: Optional[int] = None
    max_week: Optional[int] = None
    
    class Config:
        from_attributes = True

class GroupStudentSchema(BaseModel):
    id: int
    group_id: int
    student_id: int
    student_name: Optional[str] = None
    student_email: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# =============================================================================
# GROUP-STUDENT ASSOCIATION
# =============================================================================

class GroupStudent(Base):
    __tablename__ = "group_students"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    group = relationship("Group", back_populates="students")
    student = relationship("UserInDB", back_populates="groups")
    
    # Unique constraint to prevent duplicate associations
    __table_args__ = (
        UniqueConstraint('group_id', 'student_id', name='uq_group_student'),
    )

# =============================================================================
# STEP MODELS - Шаги внутри уроков
# =============================================================================

class Step(Base):
    __tablename__ = "steps"
    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    content_type = Column(String, nullable=False, default="text")  # video_text, text, quiz, flashcard, summary
    video_url = Column(String, nullable=True)
    content_text = Column(Text, nullable=True)
    original_image_url = Column(String, nullable=True)  # For SAT question images
    attachments = Column(Text, nullable=True)  # JSON array of file attachments
    order_index = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # Quiz versioning: SHA-256 hash of quiz JSON content to detect changes
    content_hash = Column(String(64), nullable=True)
    is_optional = Column(Boolean, default=False)
    
    # Relationships
    lesson = relationship("Lesson", back_populates="steps")
    favorite_flashcards = relationship("FavoriteFlashcard", back_populates="step", cascade="all, delete-orphan", passive_deletes=True)

class StepSchema(BaseModel):
    id: int
    lesson_id: int
    title: str
    content_type: str
    video_url: Optional[str] = None
    content_text: Optional[str] = None
    original_image_url: Optional[str] = None
    attachments: Optional[str] = None
    order_index: int
    created_at: datetime
    content_hash: Optional[str] = None
    is_completed: Optional[bool] = False
    is_optional: Optional[bool] = False
    
    class Config:
        from_attributes = True

class StepCreateSchema(BaseModel):
    title: str
    content_type: str = "text"
    video_url: Optional[str] = None
    content_text: Optional[str] = None
    original_image_url: Optional[str] = None
    attachments: Optional[str] = None
    order_index: int = 0
    content_hash: Optional[str] = None
    is_optional: Optional[bool] = False

# =============================================================================
# COURSE MODELS - Структура: курс → модули → уроки → шаги
# =============================================================================

class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    cover_image_url = Column(String, nullable=True)
    teacher_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    estimated_duration_minutes = Column(Integer, default=0)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    teacher = relationship("UserInDB", back_populates="created_courses")
    modules = relationship("Module", back_populates="course", cascade="all, delete-orphan", order_by="Module.order_index")
    enrollments = relationship("Enrollment", back_populates="course")
    group_access = relationship("CourseGroupAccess", back_populates="course", cascade="all, delete-orphan")
    # Head Teachers managing this course
    head_teachers = relationship("UserInDB", secondary="course_head_teachers", back_populates="managed_courses")

# =============================================================================
# HEAD TEACHER ASSOCIATION TABLE
# =============================================================================

class CourseHeadTeacher(Base):
    """Association table for Head Teachers managing Courses (M2M)."""
    __tablename__ = "course_head_teachers"
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    head_teacher_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class CourseGroupAccess(Base):
    __tablename__ = "course_group_access"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    granted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    
    # Relationships
    course = relationship("Course", back_populates="group_access")
    group = relationship("Group")
    granted_by_user = relationship("UserInDB", foreign_keys=[granted_by])

class Module(Base):
    __tablename__ = "modules"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    course = relationship("Course", back_populates="modules")
    lessons = relationship("Lesson", back_populates="module", cascade="all, delete-orphan", order_by="Lesson.order_index")

class Lesson(Base):
    __tablename__ = "lessons"
    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    duration_minutes = Column(Integer, default=0)
    order_index = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # Explicit next-lesson pointer within the same course
    next_lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=True)
    # Flag to mark lesson as initially unlocked (bypasses sequential access)
    is_initially_unlocked = Column(Boolean, default=False)
    
    # Relationships
    module = relationship("Module", back_populates="lessons")
    materials = relationship("LessonMaterial", back_populates="lesson", cascade="all, delete-orphan")
    assignments = relationship("Assignment", back_populates="lesson", cascade="all, delete-orphan")
    steps = relationship("Step", back_populates="lesson", cascade="all, delete-orphan", order_by="Step.order_index")

class LessonMaterial(Base):
    __tablename__ = "lesson_materials"
    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # pdf, docx, image, etc.
    file_url = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    lesson = relationship("Lesson", back_populates="materials")

# Course Schemas
class CourseSchema(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    teacher_id: Optional[int] = None
    teacher_name: Optional[str] = None
    estimated_duration_minutes: int
    total_modules: int = 0
    is_active: bool
    created_at: datetime
    status: Optional[str] = None
    
    class Config:
        from_attributes = True

class CourseCreateSchema(BaseModel):
    title: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    estimated_duration_minutes: int = 0
    # Allow admins to assign a teacher on course creation
    teacher_id: Optional[int] = None

class CourseGroupAccessSchema(BaseModel):
    id: int
    course_id: int
    group_id: int
    group_name: Optional[str] = None
    student_count: int = 0
    granted_by: int
    granted_by_name: Optional[str] = None
    granted_at: datetime
    is_active: bool
    
    class Config:
        from_attributes = True

class ModuleSchema(BaseModel):
    id: int
    course_id: int
    title: str
    description: Optional[str] = None
    order_index: int
    total_lessons: int = 0
    lessons: Optional[List[dict]] = None
    created_at: datetime
    is_completed: Optional[bool] = False
    
    class Config:
        from_attributes = True

class ModuleCreateSchema(BaseModel):
    title: str
    description: Optional[str] = None
    order_index: int = 0

# Base lesson schema with common fields
class BaseLessonSchema(BaseModel):
    id: int
    module_id: int
    title: str
    description: Optional[str] = None
    duration_minutes: int
    order_index: int
    created_at: datetime
    next_lesson_id: Optional[int] = None
    is_initially_unlocked: Optional[bool] = False
    steps: Optional[List[StepSchema]] = None
    is_completed: Optional[bool] = False
    
    class Config:
        from_attributes = True

# Lesson schema
class LessonSchema(BaseLessonSchema):
    total_steps: int = 0

# Legacy schema for backward compatibility (will be removed after migration)
class LegacyLessonSchema(BaseModel):
    id: int
    module_id: int
    title: str
    description: Optional[str] = None
    content_type: str
    video_url: Optional[str] = None
    content_text: Optional[str] = None
    duration_minutes: int
    order_index: int
    created_at: datetime
    quiz_data: Optional[QuizData] = None
    
    @field_validator('quiz_data', mode='before')
    @classmethod
    def parse_quiz_data(cls, v):
        if isinstance(v, str):
            try:
                return QuizData(**json.loads(v))
            except (json.JSONDecodeError, ValueError):
                return None
        return v
    
    class Config:
        from_attributes = True

class LessonCreateSchema(BaseModel):
    title: str
    description: Optional[str] = None
    duration_minutes: int = 0
    order_index: int = 0
    next_lesson_id: Optional[int] = None
    is_initially_unlocked: bool = False

class LessonMaterialSchema(BaseModel):
    id: int
    lesson_id: int
    title: str
    file_type: str
    file_url: str
    file_size_bytes: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# =============================================================================
# ASSIGNMENT MODELS - Различные типы заданий
# =============================================================================

class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=True)  # For course unit completion
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)  # For group-specific assignments
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)  # Link to calendar event (deprecated)
    lesson_number = Column(Integer, nullable=True)  # Lesson number within the group (1, 2, 3, etc.)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    assignment_type = Column(String, nullable=False)  # single_choice, multiple_choice, etc.
    content = Column(Text, nullable=False)  # JSON content with questions and options
    correct_answers = Column(Text, nullable=True)  # JSON with correct answers
    max_score = Column(Integer, default=100)
    time_limit_minutes = Column(Integer, nullable=True)
    due_date = Column(DateTime, nullable=True)  # Deadline for assignment
    file_url = Column(String, nullable=True)  # File attachment for assignment
    allowed_file_types = Column(ARRAY(String), nullable=True)  # Allowed file types for submissions
    max_file_size_mb = Column(Integer, default=10)  # Max file size in MB
    is_active = Column(Boolean, default=True)
    is_hidden = Column(Boolean, default=False)  # Hide old assignments from all users
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Late submission settings
    late_penalty_enabled = Column(Boolean, default=False)
    late_penalty_multiplier = Column(Float, default=0.6)
    
    # Relationships
    lesson = relationship("Lesson", back_populates="assignments")
    group = relationship("Group")
    event = relationship("Event")  # Link to calendar event
    submissions = relationship("AssignmentSubmission", back_populates="assignment", cascade="all, delete-orphan")

class AssignmentSubmission(Base):
    __tablename__ = "assignment_submissions"
    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    answers = Column(Text, nullable=False)  # JSON with student answers
    file_url = Column(String, nullable=True)  # File attachment for submission
    submitted_file_name = Column(String, nullable=True)  # Original filename
    score = Column(Integer, nullable=True)
    max_score = Column(Integer, nullable=False)
    is_graded = Column(Boolean, default=False)
    is_hidden = Column(Boolean, default=False)  # Teacher can hide incorrect/outdated submissions from students
    seen_by_student = Column(Boolean, default=False)  # Has student seen the graded result
    feedback = Column(Text, nullable=True)  # Teacher feedback
    graded_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Teacher who graded
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_late = Column(Boolean, default=False)
    graded_at = Column(DateTime, nullable=True)
    
    # Relationships
    assignment = relationship("Assignment", back_populates="submissions")
    user = relationship("UserInDB", foreign_keys=[user_id], back_populates="assignment_submissions")
    grader = relationship("UserInDB", foreign_keys=[graded_by])

class AssignmentLinkedLesson(Base):
    """Denormalized table for fast lookup of lessons linked to assignments"""
    __tablename__ = "assignment_linked_lessons"
    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Unique constraint
    __table_args__ = (
        UniqueConstraint('assignment_id', 'lesson_id', name='uq_assignment_lesson'),
    )

    # Relationships (optional, for backref)
    assignment = relationship("Assignment", backref="linked_lessons_rel")
    lesson = relationship("Lesson")

class AssignmentExtension(Base):
    """Individual deadline extensions for students"""
    __tablename__ = "assignment_extensions"
    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    extended_deadline = Column(DateTime, nullable=False)  # New deadline for this student
    reason = Column(Text, nullable=True)  # Optional reason for extension
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=False)  # Teacher who granted extension
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Unique constraint - one extension per student per assignment
    __table_args__ = (
        UniqueConstraint('assignment_id', 'student_id', name='uq_assignment_student_extension'),
    )
    
    # Relationships
    assignment = relationship("Assignment", backref="extensions")
    student = relationship("UserInDB", foreign_keys=[student_id], backref="assignment_extensions")
    granter = relationship("UserInDB", foreign_keys=[granted_by])

class GroupAssignment(Base):
    __tablename__ = "group_assignments"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    lesson_schedule_id = Column(Integer, ForeignKey("lesson_schedules.id", ondelete="SET NULL"), nullable=True)
    
    assigned_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    due_date = Column(DateTime, nullable=True)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    group = relationship("Group")
    assignment = relationship("Assignment")
    lesson_schedule = relationship("LessonSchedule")

class GroupAssignmentSchema(BaseModel):
    id: int
    group_id: int
    assignment_id: int
    lesson_schedule_id: Optional[int] = None
    assigned_at: datetime
    due_date: Optional[datetime] = None
    is_active: bool

    class Config:
        from_attributes = True

    @field_validator('assigned_at', 'due_date', mode='after')
    @classmethod
    def ensure_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

class AssignmentSchema(BaseModel):
    id: int
    lesson_id: Optional[int] = None
    group_id: Optional[int] = None
    event_id: Optional[int] = None  # Link to zoom lesson (Event) - deprecated
    lesson_number: Optional[int] = None  # Lesson number within group (1, 2, 3, etc.)
    title: str
    description: Optional[str] = None
    assignment_type: str
    content: dict
    max_score: int
    time_limit_minutes: Optional[int] = None
    due_date: Optional[datetime] = None
    event_start_datetime: Optional[datetime] = None # Added for display
    file_url: Optional[str] = None
    allowed_file_types: Optional[List[str]] = None
    max_file_size_mb: int = 10
    is_active: bool
    is_hidden: Optional[bool] = False
    late_penalty_enabled: Optional[bool] = False
    late_penalty_multiplier: Optional[float] = 0.6
    created_at: datetime
    
    @field_validator('content', mode='before')
    @classmethod
    def parse_content(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v

    @field_validator('due_date', 'event_start_datetime', 'created_at', mode='after')
    @classmethod
    def ensure_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v
    
    class Config:
        from_attributes = True

class AssignmentCreateSchema(BaseModel):
    title: str
    description: Optional[str] = None
    assignment_type: str
    content: dict
    correct_answers: Optional[dict] = None
    max_score: int = 100
    time_limit_minutes: Optional[int] = None
    due_date: Optional[datetime] = None
    group_id: Optional[int] = None
    group_ids: Optional[List[int]] = None
    event_id: Optional[int] = None  # Link to calendar event (deprecated)
    event_mapping: Optional[Dict[int, int]] = None  # Map group_id -> event_id (deprecated)
    lesson_number_mapping: Optional[Dict[int, int]] = None  # Map group_id -> lesson_number
    due_date_mapping: Optional[Dict[int, datetime]] = None # Map group_id -> specific due_date
    allowed_file_types: Optional[List[str]] = None
    max_file_size_mb: int = 10
    
    late_penalty_enabled: bool = False
    late_penalty_multiplier: float = 0.6
    
    @field_validator('content')
    @classmethod
    def validate_multi_task_content(cls, v, info):
        """Validate content structure for multi_task assignments"""
        if info.data.get('assignment_type') == 'multi_task':
            if 'tasks' not in v:
                raise ValueError("multi_task assignment must have 'tasks' array in content")
            if not isinstance(v['tasks'], list) or len(v['tasks']) == 0:
                raise ValueError("multi_task assignment must have at least one task")
        return v

class AssignmentSubmissionSchema(BaseModel):
    id: int
    assignment_id: int
    user_id: int
    user_name: Optional[str] = None
    answers: dict
    file_url: Optional[str] = None
    submitted_file_name: Optional[str] = None
    score: Optional[int] = None
    max_score: int
    is_graded: bool
    is_hidden: Optional[bool] = False
    feedback: Optional[str] = None
    graded_by: Optional[int] = None
    grader_name: Optional[str] = None
    submitted_at: datetime
    is_late: Optional[bool] = False
    graded_at: Optional[datetime] = None
    
    @field_validator('answers', mode='before')
    @classmethod
    def parse_answers(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v
    
    class Config:
        from_attributes = True

class GradeSubmissionSchema(BaseModel):
    score: int
    feedback: Optional[str] = None

class SubmitAssignmentSchema(BaseModel):
    answers: dict
    file_url: Optional[str] = None
    submitted_file_name: Optional[str] = None

class AssignmentExtensionSchema(BaseModel):
    id: int
    assignment_id: int
    student_id: int
    student_name: Optional[str] = None
    extended_deadline: datetime
    reason: Optional[str] = None
    granted_by: int
    granter_name: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class GrantExtensionSchema(BaseModel):
    student_id: int
    extended_deadline: datetime
    reason: Optional[str] = None

# =============================================================================
# PROGRESS TRACKING MODELS
# =============================================================================

class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    enrolled_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("UserInDB", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")

class StudentProgress(Base):
    __tablename__ = "student_progress"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=True)
    
    # Progress tracking
    status = Column(String, nullable=False, default="not_started")  # not_started, in_progress, completed
    completion_percentage = Column(Integer, default=0)  # 0-100
    time_spent_minutes = Column(Integer, default=0)
    last_accessed = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("UserInDB", back_populates="progress_records")
    course = relationship("Course")
    lesson = relationship("Lesson")
    assignment = relationship("Assignment")

class StepProgress(Base):
    __tablename__ = "step_progress"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(Integer, ForeignKey("steps.id", ondelete="CASCADE"), nullable=False)
    
    # Progress tracking
    status = Column(String, nullable=False, default="not_started")  # not_started, in_progress, completed
    started_at = Column(DateTime, nullable=True)  # Время начала изучения шага
    visited_at = Column(DateTime, nullable=True)  # Время последнего посещения
    completed_at = Column(DateTime, nullable=True)  # Время завершения
    time_spent_minutes = Column(Integer, default=0)
    
    # Relationships
    user = relationship("UserInDB")
    course = relationship("Course")
    lesson = relationship("Lesson")
    step = relationship("Step")
    
    # Unique constraint to prevent duplicate progress records
    __table_args__ = (
        UniqueConstraint('user_id', 'step_id', name='uq_user_step_progress'),
    )

class ProgressSnapshot(Base):
    """Модель для хранения снимков прогресса студентов для отслеживания динамики"""
    __tablename__ = "progress_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True)  # None для общего прогресса
    snapshot_date = Column(Date, nullable=False, default=date.today)
    
    # Метрики прогресса на момент снимка
    completed_steps = Column(Integer, default=0, nullable=False)
    total_steps = Column(Integer, default=0, nullable=False)
    completion_percentage = Column(Float, default=0.0, nullable=False)
    total_time_spent_minutes = Column(Integer, default=0, nullable=False)
    assignments_completed = Column(Integer, default=0, nullable=False)
    total_assignments = Column(Integer, default=0, nullable=False)
    assignment_score_percentage = Column(Float, default=0.0, nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("UserInDB")
    course = relationship("Course")
    
    # Уникальный индекс для предотвращения дублирования снимков
    __table_args__ = (
        UniqueConstraint('user_id', 'course_id', 'snapshot_date', name='uq_progress_snapshot'),
    )

# =============================================================================
# CACHE MODELS - Pre-computed summaries for efficient analytics
# =============================================================================

class StudentCourseSummary(Base):
    """Pre-computed summary of student progress per course - updated on step completion.
    
    This table eliminates N+1 queries in analytics endpoints by caching:
    - Progress metrics (steps completed, completion percentage)
    - Time tracking (total time spent)
    - Assignment metrics (completed, scores)
    - Last activity information
    """
    __tablename__ = "student_course_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    
    # Progress metrics (updated incrementally on step completion)
    total_steps = Column(Integer, default=0)
    completed_steps = Column(Integer, default=0)
    completion_percentage = Column(Float, default=0.0)
    
    # Time tracking
    total_time_spent_minutes = Column(Integer, default=0)
    
    # Assignment metrics
    total_assignments = Column(Integer, default=0)
    completed_assignments = Column(Integer, default=0)
    total_assignment_score = Column(Float, default=0.0)
    max_possible_score = Column(Float, default=0.0)
    average_assignment_percentage = Column(Float, default=0.0)
    
    # Last activity tracking
    last_activity_at = Column(DateTime, nullable=True)
    last_lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True)
    last_lesson_title = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("UserInDB")
    course = relationship("Course")
    last_lesson = relationship("Lesson")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'course_id', name='uq_user_course_summary'),
        Index('idx_user_course_summary', 'user_id', 'course_id'),
    )


class CourseAnalyticsCache(Base):
    """Pre-computed course analytics - updated periodically or on-demand.
    
    Caches aggregate metrics for course-level dashboards:
    - Student enrollment counts
    - Average progress across all students
    - Content counts (modules, lessons, steps)
    """
    __tablename__ = "course_analytics_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Student counts
    total_enrolled = Column(Integer, default=0)
    active_students_7d = Column(Integer, default=0)  # Active in last 7 days
    active_students_30d = Column(Integer, default=0)  # Active in last 30 days
    
    # Aggregate progress metrics
    average_completion_percentage = Column(Float, default=0.0)
    average_assignment_score = Column(Float, default=0.0)
    
    # Content counts (denormalized for fast lookups)
    total_modules = Column(Integer, default=0)
    total_lessons = Column(Integer, default=0)
    total_steps = Column(Integer, default=0)
    total_assignments = Column(Integer, default=0)
    
    # Timestamps
    last_calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    course = relationship("Course")


# Pydantic schemas for cache models
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


class QuizAttempt(Base):
    """Модель для хранения попыток прохождения квизов"""
    __tablename__ = "quiz_attempts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    step_id = Column(Integer, ForeignKey("steps.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    quiz_title = Column(String, nullable=True)
    total_questions = Column(Integer, nullable=False)
    correct_answers = Column(Integer, nullable=False)
    score_percentage = Column(Float, nullable=False)
    answers = Column(Text, nullable=True)  # JSON string of user answers
    time_spent_seconds = Column(Integer, nullable=True)
    completed_at = Column(DateTime, nullable=True)  # NULL for drafts
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))  # Track last update
    
    # Draft/In-progress support
    is_draft = Column(Boolean, default=False, nullable=False)  # True = in-progress, not submitted
    current_question_index = Column(Integer, default=0, nullable=True)  # Track progress position
    
    # Quiz versioning: hash of quiz content at time of attempt
    quiz_content_hash = Column(String(64), nullable=True)
    
    # Grading fields
    is_graded = Column(Boolean, default=True)  # True for auto-graded, False for manual grading required
    feedback = Column(Text, nullable=True)
    graded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    graded_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("UserInDB", foreign_keys=[user_id])
    step = relationship("Step")
    course = relationship("Course")
    lesson = relationship("Lesson")
    grader = relationship("UserInDB", foreign_keys=[graded_by])

# Progress Schemas
class EnrollmentSchema(BaseModel):
    id: int
    user_id: int
    course_id: int
    enrolled_at: datetime
    completed_at: Optional[datetime] = None
    is_active: bool
    
    class Config:
        from_attributes = True

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
    completed_at: Optional[datetime] = None  # NULL for drafts
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Draft/In-progress support
    is_draft: bool = False
    current_question_index: Optional[int] = None
    quiz_content_hash: Optional[str] = None
    
    # Grading fields
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
    correct_answers: int = 0  # Default 0 for drafts
    score_percentage: float = 0  # Default 0 for drafts
    answers: Optional[str] = None
    time_spent_seconds: Optional[int] = None
    is_graded: bool = True  # Default to True (auto-graded)
    is_draft: bool = False  # True = save as draft/in-progress
    current_question_index: Optional[int] = None  # Track progress position
    quiz_content_hash: Optional[str] = None  # Hash of quiz content at attempt time


class QuizAttemptUpdateSchema(BaseModel):
    """Schema for updating a quiz draft"""
    answers: Optional[str] = None
    current_question_index: Optional[int] = None
    time_spent_seconds: Optional[int] = None
    # For finalizing the quiz
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

# =============================================================================
# MESSAGE MODELS (Встроенный чат)
# =============================================================================

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    sender = relationship("UserInDB", foreign_keys=[from_user_id], back_populates="sent_messages")
    recipient = relationship("UserInDB", foreign_keys=[to_user_id], back_populates="received_messages")

class MessageSchema(BaseModel):
    id: int
    from_user_id: int
    to_user_id: int
    sender_name: Optional[str] = None
    recipient_name: Optional[str] = None
    content: str
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class SendMessageSchema(BaseModel):
    to_user_id: int
    content: str

# =============================================================================
# DASHBOARD SCHEMAS
# =============================================================================

class DashboardStatsSchema(BaseModel):
    user: dict
    stats: dict
    recent_courses: List[dict]

class CourseProgressSchema(BaseModel):
    course_id: int
    course_title: str
    teacher_name: str
    cover_image_url: Optional[str] = None
    total_modules: int
    completion_percentage: int
    status: str
    last_accessed: Optional[datetime] = None

# =============================================================================
# NOTIFICATION MODELS (Internal platform notifications)
# =============================================================================

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    notification_type = Column(String, nullable=False)  # assignment, message, course, system
    related_id = Column(Integer, nullable=True)  # ID of related object (assignment, course, etc.)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("UserInDB", back_populates="notifications")

class NotificationSchema(BaseModel):
    id: int
    user_id: int
    title: str
    content: str
    notification_type: str
    related_id: Optional[int] = None
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# =============================================================================
# EVENT MODELS - Schedule and Events Management
# =============================================================================

class Event(Base):
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(String, nullable=False)  # "class", "weekly_test", "webinar"
    start_datetime = Column(DateTime, nullable=False)
    end_datetime = Column(DateTime, nullable=False)
    location = Column(String, nullable=True)  # Аудитория или ссылка
    is_online = Column(Boolean, default=True)
    meeting_url = Column(String, nullable=True)  # Zoom/Teams ссылка
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    is_recurring = Column(Boolean, default=False)  # Для уикли тестов
    recurrence_pattern = Column(String, nullable=True)  # "weekly", "daily"
    recurrence_end_date = Column(Date, nullable=True)  # Когда заканчивается повторение
    max_participants = Column(Integer, nullable=True)  # Для вебинаров
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Assigned teacher
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    creator = relationship("UserInDB", foreign_keys=[created_by])
    event_groups = relationship("EventGroup", back_populates="event", cascade="all, delete-orphan")
    event_courses = relationship("EventCourse", back_populates="event", cascade="all, delete-orphan")
    event_participants = relationship("EventParticipant", back_populates="event", cascade="all, delete-orphan")
    teacher = relationship("UserInDB", foreign_keys=[teacher_id])

    @property
    def is_substitution(self):
        """Check if the assigned teacher is different from the group's teacher."""
        if self.teacher_id and self.event_groups:
            # We assume the event belongs to at least one group.
            # Use the first group's teacher for comparison.
            # Requires eager loading of event_groups.group
            try:
                first_group_assoc = self.event_groups[0]
                if first_group_assoc.group and first_group_assoc.group.teacher_id:
                    return self.teacher_id != first_group_assoc.group.teacher_id
            except (IndexError, AttributeError):
                pass
        return False

    @property
    def teacher_name(self):
        """Return the name of the assigned teacher."""
        return self.teacher.name if self.teacher else None

class EventGroup(Base):
    __tablename__ = "event_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    event = relationship("Event", back_populates="event_groups")
    group = relationship("Group")
    
    # Unique constraint to prevent duplicate associations
    __table_args__ = (
        UniqueConstraint('event_id', 'group_id', name='uq_event_group'),
    )

class EventCourse(Base):
    __tablename__ = "event_courses"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    event = relationship("Event", back_populates="event_courses")
    course = relationship("Course")
    
    # Unique constraint to prevent duplicate associations
    __table_args__ = (
        UniqueConstraint('event_id', 'course_id', name='uq_event_course'),
    )

class EventParticipant(Base):
    __tablename__ = "event_participants"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    registration_status = Column(String, default="registered")  # "registered", "attended", "missed"
    registered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    attended_at = Column(DateTime, nullable=True)
    activity_score = Column(Float, nullable=True)  # Activity score out of 10
    
    # Relationships
    event = relationship("Event", back_populates="event_participants")
    user = relationship("UserInDB")
    
    # Unique constraint to prevent duplicate registrations
    __table_args__ = (
        UniqueConstraint('event_id', 'user_id', name='uq_event_participant'),
    )


class MissedAttendanceLog(Base):
    """
    Logs when a teacher misses recording attendance for an event.
    Once recorded, this log persists even after attendance is later filled.
    """
    __tablename__ = "missed_attendance_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # When this was detected as missing
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Expected vs recorded at time of detection
    expected_count = Column(Integer, nullable=False)
    recorded_count_at_detection = Column(Integer, default=0)
    
    # When/if attendance was later filled
    resolved_at = Column(DateTime, nullable=True)
    resolved_count = Column(Integer, nullable=True)  # How many were recorded when resolved
    
    # Relationships
    event = relationship("Event")
    group = relationship("Group")
    teacher = relationship("UserInDB")
    
    # Unique constraint - one log per event+group combination
    __table_args__ = (
        UniqueConstraint('event_id', 'group_id', name='uq_missed_attendance_event_group'),
        Index('ix_missed_attendance_teacher', 'teacher_id'),
        Index('ix_missed_attendance_resolved', 'resolved_at'),
    )


# Pydantic schemas for Events
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
    groups: Optional[List[str]] = None  # List of group names
    courses: Optional[List[str]] = None # List of course names
    group_ids: Optional[List[int]] = None # List of group IDs
    course_ids: Optional[List[int]] = None # List of course IDs
    created_at: datetime
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
    event_type: str  # "class", "weekly_test", "webinar"
    start_datetime: datetime
    end_datetime: datetime
    location: Optional[str] = None
    is_online: bool = True
    meeting_url: Optional[str] = None
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None  # "weekly", "daily"
    recurrence_end_date: Optional[date] = None
    max_participants: Optional[int] = None
    teacher_id: Optional[int] = None
    group_ids: List[int] = []  # List of group IDs to assign event to
    course_ids: List[int] = [] # List of course IDs to assign event to

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
    status: str  # "attended", "missed", "late"

class AttendanceBulkUpdateSchema(BaseModel):
    attendance: List[AttendanceRecord]

class EventStudentSchema(BaseModel):
    student_id: int
    name: str
    attendance_status: Optional[str] = "registered" # "attended", "missed", "late", "registered"
    last_updated: Optional[datetime] = None
# =============================================================================
# LEADERBOARD MODELS
# =============================================================================
# LEADERSHIP / CURATOR MODELS
# =============================================================================

class LessonSchedule(Base):
    __tablename__ = "lesson_schedules"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    week_number = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Unique constraint: only one schedule per group at a given time
    __table_args__ = (
        UniqueConstraint('group_id', 'scheduled_at', name='uq_lesson_schedule_group_time'),
    )
    
    # Relationships
    group = relationship("Group", backref="lesson_schedules")
    lesson = relationship("Lesson")
    attendances = relationship("Attendance", back_populates="lesson_schedule", cascade="all, delete-orphan")

class Attendance(Base):
    __tablename__ = "attendances"
    id = Column(Integer, primary_key=True, index=True)
    lesson_schedule_id = Column(Integer, ForeignKey("lesson_schedules.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, default="present") # present, absent, late, excused
    score = Column(Integer, default=0) # 0, 5, 12, 15
    activity_score = Column(Float, nullable=True)  # Activity score out of 10
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    lesson_schedule = relationship("LessonSchedule", back_populates="attendances")
    user = relationship("UserInDB")

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


class LeaderboardEntry(Base):
    __tablename__ = "leaderboard_entries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    week_number = Column(Integer, nullable=False)
    
    # Manual scores - Lessons (Participation/Attendance)
    lesson_1 = Column(Float, default=0.0)
    lesson_2 = Column(Float, default=0.0)
    lesson_3 = Column(Float, default=0.0)
    lesson_4 = Column(Float, default=0.0)
    lesson_5 = Column(Float, default=0.0)

    # Manual scores - Other
    curator_hour = Column(Float, default=0.0)
    mock_exam = Column(Float, default=0.0)
    study_buddy = Column(Float, default=0.0)
    self_reflection_journal = Column(Float, default=0.0)
    weekly_evaluation = Column(Float, default=0.0)
    extra_points = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
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
    
    # Visibility settings for manual columns
    curator_hour_enabled = Column(Boolean, default=True)
    curator_hour_date = Column(Date, nullable=True)
    study_buddy_enabled = Column(Boolean, default=True)
    self_reflection_journal_enabled = Column(Boolean, default=True)
    weekly_evaluation_enabled = Column(Boolean, default=True)
    extra_points_enabled = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    group = relationship("Group", foreign_keys=[group_id])
    __table_args__ = (
        UniqueConstraint('group_id', 'week_number', name='uq_leaderboard_config'),
    )

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

# =============================================================================
# CURATOR EVALUATION MODELS
# =============================================================================

class CuratorRating(Base):
    """Head Curator's manual evaluation of other curators."""
    __tablename__ = "curator_ratings"
    id = Column(Integer, primary_key=True, index=True)
    curator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    head_curator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    week_number = Column(Integer, nullable=False)
    
    # Metrics (0-10 scale)
    professionalism = Column(Float, default=0.0)
    responsiveness = Column(Float, default=0.0)
    feedback_quality = Column(Float, default=0.0)
    retention_rate = Column(Float, default=0.0)
    
    extra_points = Column(Float, default=0.0)
    comment = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    curator = relationship("UserInDB", foreign_keys=[curator_id])
    head_curator = relationship("UserInDB", foreign_keys=[head_curator_id])
    
    __table_args__ = (
        UniqueConstraint('curator_id', 'week_number', name='uq_curator_rating_week'),
    )

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



# =============================================================================
# QUESTION ERROR REPORTS
# =============================================================================

class QuestionErrorReport(Base):
    """Model for tracking error reports submitted by users for quiz questions."""
    __tablename__ = "question_error_reports"
    
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(String(255), nullable=False, index=True)  # ID of the question from quiz content
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(Integer, ForeignKey("steps.id", ondelete="SET NULL"), nullable=True)
    message = Column(Text, nullable=False)
    suggested_answer = Column(Text, nullable=True)  # User's suggested correct answer
    status = Column(String, default="pending", nullable=False)  # pending, reviewed, resolved, dismissed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    user = relationship("UserInDB", foreign_keys=[user_id])
    step = relationship("Step", foreign_keys=[step_id])
    resolver = relationship("UserInDB", foreign_keys=[resolved_by])


# =============================================================================
# MANUAL LESSON UNLOCKS
# =============================================================================

class ManualLessonUnlock(Base):
    """Model for tracking units (lessons) manually unlocked by teachers for students or groups."""
    __tablename__ = "manual_lesson_unlocks"
    
    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True, index=True)
    granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    lesson = relationship("Lesson")
    user = relationship("UserInDB", foreign_keys=[user_id])
    group = relationship("Group", foreign_keys=[group_id])
    granter = relationship("UserInDB", foreign_keys=[granted_by])

    __table_args__ = (
        UniqueConstraint('lesson_id', 'user_id', name='uq_manual_unlock_user'),
        UniqueConstraint('lesson_id', 'group_id', name='uq_manual_unlock_group'),
    )

class ManualLessonUnlockSchema(BaseModel):
    id: int
    lesson_id: int
    user_id: Optional[int] = None
    group_id: Optional[int] = None
    granted_by: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class ManualLessonUnlockCreateSchema(BaseModel):
    lesson_id: int
    user_id: Optional[int] = None
    group_id: Optional[int] = None
    unlock_all_teacher_groups: Optional[bool] = False


# =============================================================================
# DAILY QUESTION COMPLETIONS
# =============================================================================

class DailyQuestionCompletion(Base):
    """Tracks when a student completes their daily recommended questions."""
    __tablename__ = "daily_question_completions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    completed_date = Column(Date, nullable=False, index=True)
    questions_data = Column(JSON, nullable=True)  # Store which questions were answered
    score = Column(Integer, nullable=True)  # Number of correct answers
    total_questions = Column(Integer, nullable=True)  # Total number of questions
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("UserInDB", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint('user_id', 'completed_date', name='uq_daily_question_user_date'),
    )


# =============================================================================
# LESSON SUBSTITUTION / RESCHEDULE REQUESTS
# =============================================================================

class LessonRequest(Base):
    """Model for lesson substitution and reschedule requests."""
    __tablename__ = "lesson_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_type = Column(String, nullable=False)  # 'substitution' or 'reschedule'
    status = Column(String, default="pending", nullable=False)  # pending_teacher, pending, approved, rejected

    # The teacher who created the request
    requester_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Original lesson info
    lesson_schedule_id = Column(Integer, ForeignKey("lesson_schedules.id", ondelete="SET NULL"), nullable=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    original_datetime = Column(DateTime, nullable=False)

    # Substitution: who will replace (primary chosen by admin)
    substitute_teacher_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # JSON array of candidate teacher IDs suggested by requester
    substitute_teacher_ids = Column(Text, nullable=True)  # JSON string e.g. "[1,2,3]"

    # Confirmed substitute teacher (the one who accepted)
    confirmed_teacher_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Reschedule: new datetime
    new_datetime = Column(DateTime, nullable=True)

    reason = Column(Text, nullable=True)
    admin_comment = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    requester = relationship("UserInDB", foreign_keys=[requester_id])
    substitute_teacher = relationship("UserInDB", foreign_keys=[substitute_teacher_id])
    confirmed_teacher = relationship("UserInDB", foreign_keys=[confirmed_teacher_id])
    resolver = relationship("UserInDB", foreign_keys=[resolved_by])
    lesson_schedule = relationship("LessonSchedule", foreign_keys=[lesson_schedule_id])
    event = relationship("Event", foreign_keys=[event_id])
    group = relationship("Group", foreign_keys=[group_id])


class LessonRequestSchema(BaseModel):
    id: int
    request_type: str
    status: str
    requester_id: int
    requester_name: Optional[str] = None
    lesson_schedule_id: Optional[int] = None
    event_id: Optional[int] = None
    group_id: int
    group_name: Optional[str] = None
    original_datetime: datetime
    substitute_teacher_id: Optional[int] = None
    substitute_teacher_name: Optional[str] = None
    substitute_teacher_ids: Optional[list] = None
    substitute_teacher_names: Optional[list] = None
    confirmed_teacher_id: Optional[int] = None
    confirmed_teacher_name: Optional[str] = None
    new_datetime: Optional[datetime] = None
    reason: Optional[str] = None
    admin_comment: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = None

    class Config:
        from_attributes = True


class CreateLessonRequestSchema(BaseModel):
    request_type: str  # 'substitution' or 'reschedule'
    lesson_schedule_id: Optional[int] = None
    event_id: Optional[int] = None
    group_id: int
    original_datetime: datetime
    substitute_teacher_ids: Optional[list] = None  # list of candidate teacher IDs
    substitute_teacher_id: Optional[int] = None  # for backward compat
    new_datetime: Optional[datetime] = None  # for reschedule
    reason: Optional[str] = None


class ResolveLessonRequestSchema(BaseModel):
    admin_comment: Optional[str] = None
