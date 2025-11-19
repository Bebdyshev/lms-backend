"""
Utility functions for calculating course and lesson durations based on content.
"""
import re
import json
from typing import Optional
from sqlalchemy.orm import Session
from src.schemas.models import Course, Module, Lesson, Step


def extract_video_duration_from_url(video_url: str) -> int:
    """
    Extract video duration from YouTube URL if available.
    For now, returns a default estimate. Could be enhanced with YouTube API.
    
    Args:
        video_url: YouTube video URL
        
    Returns:
        Estimated duration in minutes (default: 10 minutes)
    """
    # TODO: Integrate with YouTube API to get actual duration
    # For now, return a reasonable default
    return 10


def estimate_reading_time(text: str) -> int:
    """
    Estimate reading time based on text length.
    Average reading speed: ~200-250 words per minute.
    
    Args:
        text: Text content to estimate
        
    Returns:
        Estimated reading time in minutes
    """
    if not text:
        return 0
    
    # Count words
    words = len(text.split())
    
    # Average reading speed: 200 words per minute
    minutes = max(1, round(words / 200))
    
    return minutes


def estimate_quiz_time(content_text: str) -> int:
    """
    Estimate time to complete a quiz based on number of questions.
    Average: 1-2 minutes per question.
    
    Args:
        content_text: JSON string containing quiz data
        
    Returns:
        Estimated quiz time in minutes
    """
    if not content_text:
        return 5  # Default for empty quiz
    
    try:
        quiz_data = json.loads(content_text)
        questions = quiz_data.get('questions', [])
        num_questions = len(questions)
        
        # Estimate 1.5 minutes per question
        return max(5, num_questions * 2)
    except (json.JSONDecodeError, TypeError):
        return 5  # Default fallback


def estimate_flashcard_time(content_text: str) -> int:
    """
    Estimate time to review flashcards.
    Average: 30 seconds per card.
    
    Args:
        content_text: JSON string containing flashcard data
        
    Returns:
        Estimated review time in minutes
    """
    if not content_text:
        return 3  # Default
    
    try:
        flashcard_data = json.loads(content_text)
        cards = flashcard_data.get('cards', [])
        num_cards = len(cards)
        
        # Estimate 0.5 minutes (30 seconds) per card
        return max(3, round(num_cards * 0.5))
    except (json.JSONDecodeError, TypeError):
        return 3  # Default fallback


def calculate_step_duration(step: Step) -> int:
    """
    Calculate estimated duration for a single step based on its content type.
    
    Args:
        step: Step object
        
    Returns:
        Estimated duration in minutes
    """
    duration = 0
    
    if step.content_type == 'video_text':
        # Video + text content
        if step.video_url:
            duration += extract_video_duration_from_url(step.video_url)
        if step.content_text:
            duration += estimate_reading_time(step.content_text)
    
    elif step.content_type == 'text':
        # Text-only content
        if step.content_text:
            duration += estimate_reading_time(step.content_text)
        else:
            duration = 2  # Minimum for text step
    
    elif step.content_type == 'quiz':
        # Quiz content
        duration += estimate_quiz_time(step.content_text)
    
    elif step.content_type == 'flashcard':
        # Flashcard content
        duration += estimate_flashcard_time(step.content_text)
    
    else:
        # Unknown content type
        duration = 5  # Default
    
    return max(1, duration)  # Minimum 1 minute


def calculate_lesson_duration(lesson: Lesson, db: Session) -> int:
    """
    Calculate total duration for a lesson by summing all its steps.
    
    Args:
        lesson: Lesson object
        db: Database session
        
    Returns:
        Total estimated duration in minutes
    """
    steps = db.query(Step).filter(Step.lesson_id == lesson.id).all()
    
    total_duration = 0
    for step in steps:
        total_duration += calculate_step_duration(step)
    
    return total_duration


def calculate_module_duration(module: Module, db: Session) -> int:
    """
    Calculate total duration for a module by summing all its lessons.
    
    Args:
        module: Module object
        db: Database session
        
    Returns:
        Total estimated duration in minutes
    """
    lessons = db.query(Lesson).filter(Lesson.module_id == module.id).all()
    
    total_duration = 0
    for lesson in lessons:
        total_duration += calculate_lesson_duration(lesson, db)
    
    return total_duration


def calculate_course_duration(course_id: int, db: Session) -> int:
    """
    Calculate total duration for a course by summing all its modules.
    
    Args:
        course_id: Course ID
        db: Database session
        
    Returns:
        Total estimated duration in minutes
    """
    modules = db.query(Module).filter(Module.course_id == course_id).all()
    
    total_duration = 0
    for module in modules:
        total_duration += calculate_module_duration(module, db)
    
    return total_duration


def update_course_duration(course_id: int, db: Session) -> int:
    """
    Calculate and update the estimated_duration_minutes for a course.
    
    Args:
        course_id: Course ID
        db: Database session
        
    Returns:
        Updated duration in minutes
    """
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        return 0
    
    duration = calculate_course_duration(course_id, db)
    course.estimated_duration_minutes = duration
    db.commit()
    
    return duration
