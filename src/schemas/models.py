from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Date, Time, ForeignKey, Text, Enum, ARRAY, Boolean, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, date, time, timezone
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Union
from sqlalchemy.dialects.postgresql import UUID
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

class QuizQuestion(BaseModel):
    id: str
    assignment_id: str = ""
    question_text: str
    question_type: str  # single_choice, multiple_choice, fill_blank, long_text, media_question
    options: Optional[List[QuestionOption]] = None
    correct_answer: Union[str, List[str]] = ""
    points: int = 1
    order_index: int = 0
    # New fields for enhanced question types
    media_url: Optional[str] = None  # For PDF/image attachments
    media_type: Optional[str] = None  # 'pdf', 'image'
    expected_length: Optional[int] = None  # For long text questions (character count)
    keywords: Optional[List[str]] = None  # For auto-grading long text answers

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
    task_type: str  # 'course_unit', 'file_task', 'text_task', 'link_task'
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
    step_id = Column(Integer, ForeignKey("steps.id", ondelete="CASCADE"), nullable=False)
    flashcard_id = Column(String, nullable=False)  # ID карточки внутри flashcard set
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=True)
    flashcard_data = Column(Text, nullable=False)  # JSON данные самой карточки
    created_at = Column(DateTime, default=datetime.utcnow)
    
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
    step_id: int
    flashcard_id: str
    lesson_id: Optional[int] = None
    course_id: Optional[int] = None
    flashcard_data: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class FavoriteFlashcardCreateSchema(BaseModel):
    step_id: int
    flashcard_id: str
    lesson_id: Optional[int] = None
    course_id: Optional[int] = None
    flashcard_data: str  # JSON string with FlashcardItem data

# =============================================================================
# USER MODELS - LMS PLATFORM
# =============================================================================

class UserInDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="student")  # student, teacher, curator, admin
    avatar_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    refresh_token = Column(String, nullable=True)
    
    # Onboarding tracking
    onboarding_completed = Column(Boolean, default=False, nullable=False)
    onboarding_completed_at = Column(DateTime, nullable=True)
    
    # Student specific fields
    student_id = Column(String, unique=True, nullable=True)  # For students only
    total_study_time_minutes = Column(Integer, default=0, nullable=False)
    daily_streak = Column(Integer, default=0, nullable=False)  # Current daily streak count
    last_activity_date = Column(Date, nullable=True)  # Last date when student was active
    
    # Relationships
    groups = relationship("GroupStudent", back_populates="student", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="user")
    progress_records = relationship("StudentProgress", back_populates="user")
    sent_messages = relationship("Message", foreign_keys="Message.from_user_id", back_populates="sender")
    received_messages = relationship("Message", foreign_keys="Message.to_user_id", back_populates="recipient")
    created_courses = relationship("Course", back_populates="teacher")
    assignment_submissions = relationship("AssignmentSubmission", foreign_keys="AssignmentSubmission.user_id", back_populates="user")
    favorite_flashcards = relationship("FavoriteFlashcard", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)

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
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

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
    created_at = Column(DateTime, default=datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
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
    is_completed: Optional[bool] = False
    
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

# =============================================================================
# COURSE MODELS - Структура: курс → модули → уроки → шаги
# =============================================================================

class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    cover_image_url = Column(String, nullable=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    estimated_duration_minutes = Column(Integer, default=0)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    teacher = relationship("UserInDB", back_populates="created_courses")
    modules = relationship("Module", back_populates="course", cascade="all, delete-orphan", order_by="Module.order_index")
    enrollments = relationship("Enrollment", back_populates="course")
    group_access = relationship("CourseGroupAccess", back_populates="course", cascade="all, delete-orphan")

class CourseGroupAccess(Base):
    __tablename__ = "course_group_access"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow)
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    # Explicit next-lesson pointer within the same course
    next_lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=True)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    lesson = relationship("Lesson", back_populates="materials")

# Course Schemas
class CourseSchema(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    teacher_id: int
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
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=True)  # Can be standalone
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)  # For group-specific assignments
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    lesson = relationship("Lesson", back_populates="assignments")
    group = relationship("Group")
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
    submitted_at = Column(DateTime, default=datetime.utcnow)
    graded_at = Column(DateTime, nullable=True)
    
    # Relationships
    assignment = relationship("Assignment", back_populates="submissions")
    user = relationship("UserInDB", foreign_keys=[user_id], back_populates="assignment_submissions")
    grader = relationship("UserInDB", foreign_keys=[graded_by])

# Assignment Schemas
class AssignmentSchema(BaseModel):
    id: int
    lesson_id: Optional[int] = None
    group_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    assignment_type: str
    content: dict
    max_score: int
    time_limit_minutes: Optional[int] = None
    due_date: Optional[datetime] = None
    file_url: Optional[str] = None
    allowed_file_types: Optional[List[str]] = None
    max_file_size_mb: int = 10
    is_active: bool
    is_hidden: Optional[bool] = False
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
    allowed_file_types: Optional[List[str]] = None
    max_file_size_mb: int = 10
    
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

# =============================================================================
# PROGRESS TRACKING MODELS
# =============================================================================

class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    enrolled_at = Column(DateTime, default=datetime.utcnow)
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
    last_accessed = Column(DateTime, default=datetime.utcnow)
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
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("UserInDB")
    course = relationship("Course")
    
    # Уникальный индекс для предотвращения дублирования снимков
    __table_args__ = (
        UniqueConstraint('user_id', 'course_id', 'snapshot_date', name='uq_progress_snapshot'),
    )

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
    completed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
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
    completed_at: datetime
    created_at: datetime
    
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
    correct_answers: int
    score_percentage: float
    answers: Optional[str] = None
    time_spent_seconds: Optional[int] = None
    is_graded: bool = True  # Default to True (auto-graded)

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
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("UserInDB")

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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    creator = relationship("UserInDB", foreign_keys=[created_by])
    event_groups = relationship("EventGroup", back_populates="event", cascade="all, delete-orphan")
    event_courses = relationship("EventCourse", back_populates="event", cascade="all, delete-orphan")
    event_participants = relationship("EventParticipant", back_populates="event", cascade="all, delete-orphan")

class EventGroup(Base):
    __tablename__ = "event_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
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
    registered_at = Column(DateTime, default=datetime.utcnow)
    attended_at = Column(DateTime, nullable=True)
    
    # Relationships
    event = relationship("Event", back_populates="event_participants")
    user = relationship("UserInDB")
    
    # Unique constraint to prevent duplicate registrations
    __table_args__ = (
        UniqueConstraint('event_id', 'user_id', name='uq_event_participant'),
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
    participant_count: int = 0
    groups: Optional[List[str]] = None  # List of group names
    courses: Optional[List[str]] = None # List of course names
    group_ids: Optional[List[int]] = None # List of group IDs
    course_ids: Optional[List[int]] = None # List of course IDs
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

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