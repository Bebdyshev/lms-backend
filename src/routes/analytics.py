from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, date
from io import BytesIO
import json

from src.config import get_db
from src.schemas.models import (
    StudentProgress, Course, Module, Lesson, Assignment, Enrollment, 
    UserInDB, AssignmentSubmission, StepProgress, Step, GroupStudent,
    Group, ProgressSnapshot
)
from src.routes.auth import get_current_user_dependency
from src.utils.permissions import check_course_access, check_student_access

router = APIRouter()

@router.get("/student/{student_id}/detailed")
def get_detailed_student_analytics(
    student_id: int,
    course_id: Optional[int] = None,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get comprehensive analytics for a specific student"""
    
    # Check permissions
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Verify student exists
    student = db.query(UserInDB).filter(
        UserInDB.id == student_id, 
        UserInDB.role == "student"
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Check access rights based on role
    if current_user.role == "teacher":
        # Teachers can only see students in their courses
        teacher_courses = db.query(Course.id).filter(Course.teacher_id == current_user.id).subquery()
        student_enrollments = db.query(Enrollment).filter(
            Enrollment.user_id == student_id,
            Enrollment.course_id.in_(teacher_courses)
        ).first()
        if not student_enrollments:
            raise HTTPException(status_code=403, detail="Access denied to this student")
    
    elif current_user.role == "curator":
        # Curators can see students in their groups
        group_student = db.query(GroupStudent).filter(
            GroupStudent.student_id == student_id
        ).first()
        if not group_student:
            raise HTTPException(status_code=403, detail="Student not in any group")
        
        curator_group = db.query(Group).filter(
            Group.id == group_student.group_id,
            Group.curator_id == current_user.id
        ).first()
        if not curator_group:
            raise HTTPException(status_code=403, detail="Access denied to this student")
    
    # Get student's courses
    courses_query = db.query(Course).join(Enrollment).filter(
        Enrollment.user_id == student_id,
        Enrollment.is_active == True,
        Course.is_active == True
    )
    
    if course_id:
        courses_query = courses_query.filter(Course.id == course_id)
    
    courses = courses_query.all()
    
    analytics_data = {
        "student_info": {
            "id": student.id,
            "name": student.name,
            "email": student.email,
            "student_id": student.student_id,
            "total_study_time_minutes": student.total_study_time_minutes,
            "daily_streak": student.daily_streak,
            "last_activity_date": student.last_activity_date
        },
        "courses": []
    }
    
    for course in courses:
        # Get course modules and lessons
        modules = db.query(Module).filter(Module.course_id == course.id).order_by(Module.order_index).all()
        
        course_data = {
            "course_id": course.id,
            "course_title": course.title,
            "teacher_name": course.teacher.name if course.teacher else "Unknown",
            "modules": []
        }
        
        for module in modules:
            lessons = db.query(Lesson).filter(Lesson.module_id == module.id).order_by(Lesson.order_index).all()
            
            module_data = {
                "module_id": module.id,
                "module_title": module.title,
                "lessons": []
            }
            
            for lesson in lessons:
                # Get lesson steps
                steps = db.query(Step).filter(Step.lesson_id == lesson.id).order_by(Step.order_index).all()
                
                # Get step progress
                step_progress = db.query(StepProgress).filter(
                    StepProgress.user_id == student_id,
                    StepProgress.lesson_id == lesson.id
                ).all()
                
                # Get assignments and submissions
                assignments = db.query(Assignment).filter(Assignment.lesson_id == lesson.id).all()
                assignment_data = []
                
                for assignment in assignments:
                    submission = db.query(AssignmentSubmission).filter(
                        AssignmentSubmission.assignment_id == assignment.id,
                        AssignmentSubmission.user_id == student_id
                    ).first()
                    
                    assignment_data.append({
                        "assignment_id": assignment.id,
                        "assignment_title": assignment.title,
                        "assignment_type": assignment.assignment_type,
                        "max_score": assignment.max_score,
                        "submission": {
                            "submitted": bool(submission),
                            "score": submission.score if submission else None,
                            "submitted_at": submission.submitted_at if submission else None,
                            "is_graded": submission.is_graded if submission else False
                        } if submission else None
                    })
                
                # Analyze step completion patterns
                step_details = []
                for step in steps:
                    progress = next((sp for sp in step_progress if sp.step_id == step.id), None)
                    step_details.append({
                        "step_id": step.id,
                        "step_title": step.title,
                        "content_type": step.content_type,
                        "order_index": step.order_index,
                        "progress": {
                            "status": progress.status if progress else "not_started",
                            "visited_at": progress.visited_at if progress else None,
                            "completed_at": progress.completed_at if progress else None,
                            "time_spent_minutes": progress.time_spent_minutes if progress else 0
                        }
                    })
                
                lesson_data = {
                    "lesson_id": lesson.id,
                    "lesson_title": lesson.title,
                    "total_steps": len(steps),
                    "completed_steps": len([sp for sp in step_progress if sp.status == "completed"]),
                    "total_time_spent": sum(sp.time_spent_minutes for sp in step_progress),
                    "steps": step_details,
                    "assignments": assignment_data
                }
                
                module_data["lessons"].append(lesson_data)
            
            course_data["modules"].append(module_data)
        
        analytics_data["courses"].append(course_data)
    
    return analytics_data

@router.get("/course/{course_id}/overview")
def get_course_analytics_overview(
    course_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get analytics overview for a specific course"""
    
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check course access
    if not check_course_access(course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this course")
    
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Get enrolled students
    enrolled_students = db.query(UserInDB).join(Enrollment).filter(
        Enrollment.course_id == course_id,
        Enrollment.is_active == True,
        UserInDB.role == "student"
    ).all()
    
    # Get course structure
    modules = db.query(Module).filter(Module.course_id == course_id).order_by(Module.order_index).all()
    total_lessons = 0
    total_steps = 0
    
    for module in modules:
        lessons = db.query(Lesson).filter(Lesson.module_id == module.id).all()
        total_lessons += len(lessons)
        for lesson in lessons:
            steps = db.query(Step).filter(Step.lesson_id == lesson.id).all()
            total_steps += len(steps)
    
    # Calculate engagement metrics
    step_progress_records = db.query(StepProgress).filter(
        StepProgress.course_id == course_id
    ).all()
    
    total_time_spent = sum(sp.time_spent_minutes for sp in step_progress_records)
    completed_steps = len([sp for sp in step_progress_records if sp.status == "completed"])
    
    # Student performance summary
    student_performance = []
    for student in enrolled_students:
        student_steps = [sp for sp in step_progress_records if sp.user_id == student.id]
        student_completed = len([sp for sp in student_steps if sp.status == "completed"])
        student_time = sum(sp.time_spent_minutes for sp in student_steps)
        
        # Get assignment performance
        assignments = db.query(Assignment).join(Lesson).join(Module).filter(
            Module.course_id == course_id
        ).all()
        
        total_assignments = len(assignments)
        completed_assignments = 0
        total_score = 0
        max_possible_score = 0
        
        for assignment in assignments:
            submission = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.assignment_id == assignment.id,
                AssignmentSubmission.user_id == student.id
            ).first()
            
            if submission:
                completed_assignments += 1
                if submission.score is not None:
                    total_score += submission.score
                    max_possible_score += submission.max_score
        
        student_performance.append({
            "student_id": student.id,
            "student_name": student.name,
            "completed_steps": student_completed,
            "total_steps_available": total_steps,
            "completion_percentage": (student_completed / total_steps * 100) if total_steps > 0 else 0,
            "time_spent_minutes": student_time,
            "completed_assignments": completed_assignments,
            "total_assignments": total_assignments,
            "assignment_score_percentage": (total_score / max_possible_score * 100) if max_possible_score > 0 else 0
        })
    
    return {
        "course_info": {
            "id": course.id,
            "title": course.title,
            "teacher_name": course.teacher.name if course.teacher else "Unknown"
        },
        "structure": {
            "total_modules": len(modules),
            "total_lessons": total_lessons,
            "total_steps": total_steps
        },
        "engagement": {
            "total_enrolled_students": len(enrolled_students),
            "total_time_spent_minutes": total_time_spent,
            "total_completed_steps": completed_steps,
            "average_completion_rate": (completed_steps / (total_steps * len(enrolled_students)) * 100) if total_steps > 0 and enrolled_students else 0
        },
        "student_performance": student_performance
    }

@router.get("/video-engagement/{course_id}")
def get_video_engagement_analytics(
    course_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get video engagement analytics for a course"""
    
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not check_course_access(course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this course")
    
    # Get video steps in the course
    video_steps = db.query(Step).join(Lesson).join(Module).filter(
        Module.course_id == course_id,
        Step.content_type == "video_text"
    ).all()
    
    video_analytics = []
    
    for step in video_steps:
        # Get progress for this video step
        step_progress = db.query(StepProgress).filter(
            StepProgress.step_id == step.id
        ).all()
        
        total_views = len(step_progress)
        completed_views = len([sp for sp in step_progress if sp.status == "completed"])
        total_time_spent = sum(sp.time_spent_minutes for sp in step_progress)
        
        video_analytics.append({
            "step_id": step.id,
            "step_title": step.title,
            "lesson_title": step.lesson.title if step.lesson else "Unknown",
            "video_url": step.video_url,
            "total_views": total_views,
            "completed_views": completed_views,
            "completion_rate": (completed_views / total_views * 100) if total_views > 0 else 0,
            "average_watch_time_minutes": (total_time_spent / total_views) if total_views > 0 else 0,
            "total_watch_time_minutes": total_time_spent
        })
    
    return {
        "course_id": course_id,
        "video_analytics": video_analytics,
        "summary": {
            "total_videos": len(video_steps),
            "total_video_views": sum(va["total_views"] for va in video_analytics),
            "average_completion_rate": sum(va["completion_rate"] for va in video_analytics) / len(video_analytics) if video_analytics else 0
        }
    }

@router.get("/quiz-performance/{course_id}")
def get_quiz_performance_analytics(
    course_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get quiz performance analytics for a course"""
    
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not check_course_access(course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this course")
    
    # Get quiz steps and assignments in the course
    quiz_steps = db.query(Step).join(Lesson).join(Module).filter(
        Module.course_id == course_id,
        Step.content_type == "quiz"
    ).all()
    
    quiz_assignments = db.query(Assignment).join(Lesson).join(Module).filter(
        Module.course_id == course_id,
        Assignment.assignment_type.in_(["single_choice", "multiple_choice", "fill_blank"])
    ).all()
    
    quiz_analytics = []
    
    # Analyze quiz steps
    for step in quiz_steps:
        step_progress = db.query(StepProgress).filter(
            StepProgress.step_id == step.id
        ).all()
        
        total_attempts = len(step_progress)
        completed_attempts = len([sp for sp in step_progress if sp.status == "completed"])
        
        quiz_analytics.append({
            "type": "quiz_step",
            "id": step.id,
            "title": step.title,
            "lesson_title": step.lesson.title if step.lesson else "Unknown",
            "total_attempts": total_attempts,
            "completed_attempts": completed_attempts,
            "completion_rate": (completed_attempts / total_attempts * 100) if total_attempts > 0 else 0,
            "average_time_spent": sum(sp.time_spent_minutes for sp in step_progress) / total_attempts if total_attempts > 0 else 0
        })
    
    # Analyze quiz assignments
    for assignment in quiz_assignments:
        submissions = db.query(AssignmentSubmission).filter(
            AssignmentSubmission.assignment_id == assignment.id
        ).all()
        
        total_submissions = len(submissions)
        graded_submissions = [s for s in submissions if s.is_graded and s.score is not None]
        
        if graded_submissions:
            scores = [s.score for s in graded_submissions]
            max_scores = [s.max_score for s in graded_submissions]
            average_score = sum(scores) / len(scores)
            average_percentage = sum(s.score / s.max_score * 100 for s in graded_submissions) / len(graded_submissions)
        else:
            average_score = 0
            average_percentage = 0
        
        quiz_analytics.append({
            "type": "quiz_assignment",
            "id": assignment.id,
            "title": assignment.title,
            "assignment_type": assignment.assignment_type,
            "max_score": assignment.max_score,
            "total_submissions": total_submissions,
            "graded_submissions": len(graded_submissions),
            "average_score": average_score,
            "average_percentage": average_percentage,
            "submission_rate": (total_submissions / db.query(Enrollment).filter(Enrollment.course_id == course_id).count() * 100) if db.query(Enrollment).filter(Enrollment.course_id == course_id).count() > 0 else 0
        })
    
    return {
        "course_id": course_id,
        "quiz_analytics": quiz_analytics,
        "summary": {
            "total_quizzes": len(quiz_steps) + len(quiz_assignments),
            "total_quiz_steps": len(quiz_steps),
            "total_quiz_assignments": len(quiz_assignments)
        }
    }

@router.get("/students/all")
def get_all_students_analytics(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Получить аналитику по всем доступным студентам"""
    
    # Проверка прав доступа
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Базовый запрос студентов
    students_query = db.query(UserInDB).filter(UserInDB.role == "student", UserInDB.is_active == True)
    
    # Фильтрация по ролям
    if current_user.role == "teacher":
        # Учитель видит студентов из своих групп и записанных на свои курсы
        teacher_groups = db.query(Group.id).filter(Group.teacher_id == current_user.id).subquery()
        teacher_courses = db.query(Course.id).filter(Course.teacher_id == current_user.id).subquery()
        
        group_students = db.query(GroupStudent.student_id).filter(GroupStudent.group_id.in_(teacher_groups)).subquery()
        course_students = db.query(Enrollment.user_id).filter(Enrollment.course_id.in_(teacher_courses)).subquery()
        
        students_query = students_query.filter(
            or_(
                UserInDB.id.in_(group_students),
                UserInDB.id.in_(course_students)
            )
        )
    
    elif current_user.role == "curator":
        # Куратор видит студентов из своих групп
        curator_groups = db.query(Group.id).filter(Group.curator_id == current_user.id).subquery()
        group_students = db.query(GroupStudent.student_id).filter(GroupStudent.group_id.in_(curator_groups)).subquery()
        
        students_query = students_query.filter(UserInDB.id.in_(group_students))
    
    # Админ видит всех студентов (без дополнительной фильтрации)
    
    students = students_query.all()
    
    students_analytics = []
    for student in students:
        # Получаем группы студента
        student_groups = db.query(Group).join(GroupStudent).filter(
            GroupStudent.student_id == student.id
        ).all()
        
        # Получаем ВСЕ курсы где есть прогресс студента (не через Enrollment!)
        # Используем StepProgress чтобы найти курсы где студент действительно учится
        courses_with_progress = db.query(Course).join(
            Module, Module.course_id == Course.id
        ).join(
            Lesson, Lesson.module_id == Module.id
        ).join(
            Step, Step.lesson_id == Lesson.id
        ).join(
            StepProgress, StepProgress.step_id == Step.id
        ).filter(
            StepProgress.user_id == student.id
        ).distinct().all()
        
        # Если нет прогресса, пробуем через Enrollment
        if not courses_with_progress:
            courses_with_progress = db.query(Course).join(Enrollment).filter(
                Enrollment.user_id == student.id,
                Course.is_active == True
            ).all()
        
        active_courses = courses_with_progress
        
        # Подсчитываем общий прогресс
        total_steps = 0
        completed_steps = 0
        total_assignments = 0
        completed_assignments = 0
        total_assignment_score = 0
        total_max_score = 0
        
        for course in active_courses:
            # Подсчет шагов
            course_steps = db.query(Step).join(Lesson).join(Module).filter(
                Module.course_id == course.id
            ).count()
            total_steps += course_steps
            
            # Правильный подсчет завершенных шагов через JOIN (как в детальном прогрессе)
            course_completed_steps = db.query(StepProgress).join(
                Step, StepProgress.step_id == Step.id
            ).join(
                Lesson, Step.lesson_id == Lesson.id
            ).join(
                Module, Lesson.module_id == Module.id
            ).filter(
                StepProgress.user_id == student.id,
                Module.course_id == course.id,
                StepProgress.status == "completed"
            ).count()
            completed_steps += course_completed_steps
            
            # Подсчет заданий
            course_assignments = db.query(Assignment).join(Lesson).join(Module).filter(
                Module.course_id == course.id
            ).all()
            total_assignments += len(course_assignments)
            
            for assignment in course_assignments:
                submission = db.query(AssignmentSubmission).filter(
                    AssignmentSubmission.assignment_id == assignment.id,
                    AssignmentSubmission.user_id == student.id
                ).first()
                
                if submission and submission.is_graded:
                    completed_assignments += 1
                    total_assignment_score += submission.score or 0
                    total_max_score += assignment.max_score or 0
        
        # Вычисляем проценты
        completion_percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
        assignment_score_percentage = (total_assignment_score / total_max_score * 100) if total_max_score > 0 else 0
        
        students_analytics.append({
            "student_id": student.id,
            "student_name": student.name,
            "student_email": student.email,
            "student_number": student.student_id,
            "groups": [{"id": g.id, "name": g.name} for g in student_groups],
            "active_courses_count": len(active_courses),
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "completion_percentage": round(completion_percentage, 1),
            "total_assignments": total_assignments,
            "completed_assignments": completed_assignments,
            "assignment_score_percentage": round(assignment_score_percentage, 1),
            "total_study_time_minutes": student.total_study_time_minutes,
            "daily_streak": student.daily_streak,
            "last_activity_date": student.last_activity_date
        })
    
    return {
        "students": students_analytics,
        "total_students": len(students_analytics)
    }

@router.get("/groups")
def get_groups_analytics(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Получить аналитику по всем доступным группам"""
    
    # Проверка прав доступа
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Базовый запрос групп
    groups_query = db.query(Group).filter(Group.is_active == True)
    
    # Фильтрация по ролям
    if current_user.role == "teacher":
        groups_query = groups_query.filter(Group.teacher_id == current_user.id)
    elif current_user.role == "curator":
        groups_query = groups_query.filter(Group.curator_id == current_user.id)
    
    # Админ видит все группы (без дополнительной фильтрации)
    
    groups = groups_query.all()
    
    groups_analytics = []
    for group in groups:
        # Получаем студентов группы
        students = db.query(UserInDB).join(GroupStudent).filter(
            GroupStudent.group_id == group.id,
            UserInDB.is_active == True
        ).all()
        
        # Подсчитываем средний прогресс группы
        total_completion = 0
        total_assignment_score = 0
        total_study_time = 0
        students_with_progress = 0
        
        for student in students:
            # Получаем активные курсы студента
            active_courses = db.query(Course).join(Enrollment).filter(
                Enrollment.user_id == student.id,
                Enrollment.is_active == True,
                Course.is_active == True
            ).all()
            
            if active_courses:
                student_total_steps = 0
                student_completed_steps = 0
                student_total_score = 0
                student_max_score = 0
                
                for course in active_courses:
                    # Подсчет шагов
                    course_steps = db.query(Step).join(Lesson).join(Module).filter(
                        Module.course_id == course.id
                    ).count()
                    student_total_steps += course_steps
                    
                    course_completed_steps = db.query(StepProgress).filter(
                        StepProgress.user_id == student.id,
                        StepProgress.course_id == course.id,
                        StepProgress.status == "completed"
                    ).count()
                    student_completed_steps += course_completed_steps
                    
                    # Подсчет заданий
                    assignments = db.query(Assignment).join(Lesson).join(Module).filter(
                        Module.course_id == course.id
                    ).all()
                    
                    for assignment in assignments:
                        submission = db.query(AssignmentSubmission).filter(
                            AssignmentSubmission.assignment_id == assignment.id,
                            AssignmentSubmission.user_id == student.id
                        ).first()
                        
                        if submission and submission.is_graded:
                            student_total_score += submission.score or 0
                            student_max_score += assignment.max_score or 0
                
                if student_total_steps > 0:
                    student_completion = student_completed_steps / student_total_steps * 100
                    total_completion += student_completion
                    students_with_progress += 1
                
                if student_max_score > 0:
                    total_assignment_score += student_total_score / student_max_score * 100
                
                total_study_time += student.total_study_time_minutes
        
        # Вычисляем средние значения
        avg_completion = (total_completion / students_with_progress) if students_with_progress > 0 else 0
        avg_assignment_score = (total_assignment_score / len(students)) if students else 0
        avg_study_time = (total_study_time / len(students)) if students else 0
        
        groups_analytics.append({
            "group_id": group.id,
            "group_name": group.name,
            "description": group.description,
            "teacher_name": group.teacher.name if group.teacher else None,
            "curator_name": group.curator.name if group.curator else None,
            "students_count": len(students),
            "average_completion_percentage": round(avg_completion, 1),
            "average_assignment_score_percentage": round(avg_assignment_score, 1),
            "average_study_time_minutes": round(avg_study_time, 0),
            "created_at": group.created_at
        })
    
    return {
        "groups": groups_analytics,
        "total_groups": len(groups_analytics)
    }

@router.get("/group/{group_id}/students")
def get_group_students_analytics(
    group_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Получить аналитику по студентам конкретной группы"""
    
    # Проверка прав доступа
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Проверяем доступ к группе
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Проверка прав доступа к группе
    if current_user.role == "teacher" and group.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied to this group")
    elif current_user.role == "curator" and group.curator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied to this group")
    
    # Получаем студентов группы
    students = db.query(UserInDB).join(GroupStudent).filter(
        GroupStudent.group_id == group_id,
        UserInDB.is_active == True
    ).all()
    
    students_analytics = []
    for student in students:
        # Получаем активные курсы студента
        active_courses = db.query(Course).join(Enrollment).filter(
            Enrollment.user_id == student.id,
            Enrollment.is_active == True,
            Course.is_active == True
        ).all()
        
        # Подсчитываем прогресс (аналогично предыдущему эндпоинту)
        total_steps = 0
        completed_steps = 0
        total_assignments = 0
        completed_assignments = 0
        total_assignment_score = 0
        total_max_score = 0
        
        for course in active_courses:
            course_steps = db.query(Step).join(Lesson).join(Module).filter(
                Module.course_id == course.id
            ).count()
            total_steps += course_steps
            
            course_completed_steps = db.query(StepProgress).filter(
                StepProgress.user_id == student.id,
                StepProgress.course_id == course.id,
                StepProgress.status == "completed"
            ).count()
            completed_steps += course_completed_steps
            
            course_assignments = db.query(Assignment).join(Lesson).join(Module).filter(
                Module.course_id == course.id
            ).all()
            total_assignments += len(course_assignments)
            
            for assignment in course_assignments:
                submission = db.query(AssignmentSubmission).filter(
                    AssignmentSubmission.assignment_id == assignment.id,
                    AssignmentSubmission.user_id == student.id
                ).first()
                
                if submission and submission.is_graded:
                    completed_assignments += 1
                    total_assignment_score += submission.score or 0
                    total_max_score += assignment.max_score or 0
        
        completion_percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
        assignment_score_percentage = (total_assignment_score / total_max_score * 100) if total_max_score > 0 else 0
        
        students_analytics.append({
            "student_id": student.id,
            "student_name": student.name,
            "student_email": student.email,
            "student_number": student.student_id,
            "active_courses_count": len(active_courses),
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "completion_percentage": round(completion_percentage, 1),
            "total_assignments": total_assignments,
            "completed_assignments": completed_assignments,
            "assignment_score_percentage": round(assignment_score_percentage, 1),
            "total_study_time_minutes": student.total_study_time_minutes,
            "daily_streak": student.daily_streak,
            "last_activity_date": student.last_activity_date
        })
    
    return {
        "group_info": {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "teacher_name": group.teacher.name if group.teacher else None,
            "curator_name": group.curator.name if group.curator else None
        },
        "students": students_analytics,
        "total_students": len(students_analytics)
    }

@router.get("/student/{student_id}/progress-history")
def get_student_progress_history(
    student_id: int,
    course_id: Optional[int] = None,
    days: int = Query(30, description="Number of days to look back"),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Получить историю прогресса студента"""
    
    # Проверка прав доступа
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Проверяем доступ к студенту (аналогично другим эндпоинтам)
    student = db.query(UserInDB).filter(
        UserInDB.id == student_id, 
        UserInDB.role == "student"
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Проверка прав доступа к студенту
    if current_user.role == "teacher":
        teacher_groups = db.query(Group.id).filter(Group.teacher_id == current_user.id).subquery()
        teacher_courses = db.query(Course.id).filter(Course.teacher_id == current_user.id).subquery()
        
        group_access = db.query(GroupStudent).filter(
            GroupStudent.student_id == student_id,
            GroupStudent.group_id.in_(teacher_groups)
        ).first()
        
        course_access = db.query(Enrollment).filter(
            Enrollment.user_id == student_id,
            Enrollment.course_id.in_(teacher_courses)
        ).first()
        
        if not group_access and not course_access:
            raise HTTPException(status_code=403, detail="Access denied to this student")
    
    elif current_user.role == "curator":
        curator_groups = db.query(Group.id).filter(Group.curator_id == current_user.id).subquery()
        group_access = db.query(GroupStudent).filter(
            GroupStudent.student_id == student_id,
            GroupStudent.group_id.in_(curator_groups)
        ).first()
        
        if not group_access:
            raise HTTPException(status_code=403, detail="Access denied to this student")
    
    # Получаем историю прогресса
    start_date = date.today() - timedelta(days=days)
    
    snapshots_query = db.query(ProgressSnapshot).filter(
        ProgressSnapshot.user_id == student_id,
        ProgressSnapshot.snapshot_date >= start_date
    ).order_by(ProgressSnapshot.snapshot_date)
    
    if course_id:
        snapshots_query = snapshots_query.filter(ProgressSnapshot.course_id == course_id)
    
    snapshots = snapshots_query.all()
    
    # Форматируем данные для графика
    history_data = []
    for snapshot in snapshots:
        history_data.append({
            "date": snapshot.snapshot_date.isoformat(),
            "completion_percentage": snapshot.completion_percentage,
            "completed_steps": snapshot.completed_steps,
            "total_steps": snapshot.total_steps,
            "total_time_spent_minutes": snapshot.total_time_spent_minutes,
            "assignments_completed": snapshot.assignments_completed,
            "total_assignments": snapshot.total_assignments,
            "assignment_score_percentage": snapshot.assignment_score_percentage
        })
    
    return {
        "student_info": {
            "id": student.id,
            "name": student.name,
            "student_id": student.student_id
        },
        "course_id": course_id,
        "period_days": days,
        "history": history_data
    }

def generate_student_pdf_report(student_data: dict, progress_data: dict) -> bytes:
    """Генерация PDF отчета для студента"""
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        # Заголовок отчета
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1  # Center alignment
        )
        
        story.append(Paragraph("Отчет о прогрессе студента", title_style))
        story.append(Spacer(1, 12))
        
        # Информация о студенте
        student_info = [
            ['Имя:', student_data.get('student_name', 'N/A')],
            ['Email:', student_data.get('student_email', 'N/A')],
            ['Номер студента:', student_data.get('student_number', 'N/A')],
            ['Общий прогресс:', f"{student_data.get('completion_percentage', 0)}%"],
            ['Время обучения:', f"{student_data.get('total_study_time_minutes', 0)} мин"],
            ['Дневная серия:', f"{student_data.get('daily_streak', 0)} дней"],
        ]
        
        student_table = Table(student_info, colWidths=[2*inch, 3*inch])
        student_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (1, 0), (1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(Paragraph("Информация о студенте", styles['Heading2']))
        story.append(student_table)
        story.append(Spacer(1, 12))
        
        # Прогресс по курсам
        if progress_data and 'courses' in progress_data:
            story.append(Paragraph("Прогресс по курсам", styles['Heading2']))
            
            for course in progress_data['courses']:
                story.append(Paragraph(f"Курс: {course.get('course_title', 'N/A')}", styles['Heading3']))
                
                course_info = [
                    ['Преподаватель:', course.get('teacher_name', 'N/A')],
                    ['Модули:', str(len(course.get('modules', [])))],
                ]
                
                course_table = Table(course_info, colWidths=[2*inch, 3*inch])
                course_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, -1), colors.lightblue),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                ]))
                
                story.append(course_table)
                story.append(Spacer(1, 12))
        
        # Статистика заданий
        story.append(Paragraph("Статистика выполнения заданий", styles['Heading2']))
        assignment_info = [
            ['Всего заданий:', str(student_data.get('total_assignments', 0))],
            ['Выполнено:', str(student_data.get('completed_assignments', 0))],
            ['Средний балл:', f"{student_data.get('assignment_score_percentage', 0)}%"],
        ]
        
        assignment_table = Table(assignment_info, colWidths=[2*inch, 3*inch])
        assignment_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgreen),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        
        story.append(assignment_table)
        story.append(Spacer(1, 12))
        
        # Дата генерации отчета
        story.append(Paragraph(f"Отчет сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['Normal']))
        
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
        
    except ImportError:
        # Если reportlab не установлен, возвращаем простой текстовый отчет
        report_text = f"""
ОТЧЕТ О ПРОГРЕССЕ СТУДЕНТА

Имя: {student_data.get('student_name', 'N/A')}
Email: {student_data.get('student_email', 'N/A')}
Номер студента: {student_data.get('student_number', 'N/A')}

ПРОГРЕСС:
- Общий прогресс: {student_data.get('completion_percentage', 0)}%
- Выполнено шагов: {student_data.get('completed_steps', 0)} из {student_data.get('total_steps', 0)}
- Время обучения: {student_data.get('total_study_time_minutes', 0)} минут
- Дневная серия: {student_data.get('daily_streak', 0)} дней

ЗАДАНИЯ:
- Всего заданий: {student_data.get('total_assignments', 0)}
- Выполнено: {student_data.get('completed_assignments', 0)}
- Средний балл: {student_data.get('assignment_score_percentage', 0)}%

Отчет сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}
        """
        return report_text.encode('utf-8')

@router.post("/export/student/{student_id}")
def export_student_report(
    student_id: int,
    course_id: Optional[int] = None,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Экспорт PDF отчета по студенту"""
    
    # Проверка прав доступа
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Получаем данные студента (используем существующий эндпоинт)
    try:
        # Получаем базовые данные студента из эндпоинта all students
        all_students_data = get_all_students_analytics(current_user, db)
        student_data = None
        
        for student in all_students_data['students']:
            if student['student_id'] == student_id:
                student_data = student
                break
        
        if not student_data:
            raise HTTPException(status_code=404, detail="Student not found or access denied")
        
        # Получаем детальные данные прогресса
        progress_data = get_detailed_student_analytics(student_id, course_id, current_user, db)
        
        # Генерируем PDF
        pdf_content = generate_student_pdf_report(student_data, progress_data)
        
        # Формируем имя файла
        filename = f"student_report_{student_data.get('student_number', student_id)}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

@router.post("/export/group/{group_id}")
def export_group_report(
    group_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Экспорт PDF отчета по группе"""
    
    # Проверка прав доступа
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        # Получаем данные группы
        group_data = get_group_students_analytics(group_id, current_user, db)
        
        # Генерируем PDF отчет для группы
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.lib import colors
            
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            
            # Заголовок
            story.append(Paragraph(f"Отчет по группе: {group_data['group_info']['name']}", styles['Title']))
            story.append(Spacer(1, 12))
            
            # Информация о группе
            group_info = [
                ['Название группы:', group_data['group_info']['name']],
                ['Описание:', group_data['group_info']['description'] or 'N/A'],
                ['Преподаватель:', group_data['group_info']['teacher_name'] or 'N/A'],
                ['Куратор:', group_data['group_info']['curator_name'] or 'N/A'],
                ['Количество студентов:', str(group_data['total_students'])],
            ]
            
            group_table = Table(group_info, colWidths=[2*inch, 4*inch])
            group_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
            ]))
            
            story.append(Paragraph("Информация о группе", styles['Heading2']))
            story.append(group_table)
            story.append(Spacer(1, 12))
            
            # Таблица студентов
            if group_data['students']:
                story.append(Paragraph("Студенты группы", styles['Heading2']))
                
                student_data = [['Имя', 'Email', 'Прогресс %', 'Время (мин)', 'Задания']]
                
                for student in group_data['students']:
                    student_data.append([
                        student['student_name'],
                        student['student_email'],
                        f"{student['completion_percentage']}%",
                        str(student['total_study_time_minutes']),
                        f"{student['completed_assignments']}/{student['total_assignments']}"
                    ])
                
                students_table = Table(student_data, colWidths=[1.5*inch, 2*inch, 1*inch, 1*inch, 1*inch])
                students_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                
                story.append(students_table)
            
            story.append(Spacer(1, 12))
            story.append(Paragraph(f"Отчет сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['Normal']))
            
            doc.build(story)
            buffer.seek(0)
            pdf_content = buffer.getvalue()
            
        except ImportError:
            # Fallback к текстовому отчету
            report_text = f"""
ОТЧЕТ ПО ГРУППЕ: {group_data['group_info']['name']}

ИНФОРМАЦИЯ О ГРУППЕ:
- Описание: {group_data['group_info']['description'] or 'N/A'}
- Преподаватель: {group_data['group_info']['teacher_name'] or 'N/A'}
- Куратор: {group_data['group_info']['curator_name'] or 'N/A'}
- Количество студентов: {group_data['total_students']}

СТУДЕНТЫ:
"""
            for student in group_data['students']:
                report_text += f"""
- {student['student_name']} ({student['student_email']})
  Прогресс: {student['completion_percentage']}%
  Время обучения: {student['total_study_time_minutes']} мин
  Задания: {student['completed_assignments']}/{student['total_assignments']}
"""
            
            report_text += f"\nОтчет сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            pdf_content = report_text.encode('utf-8')
        
        filename = f"group_report_{group_data['group_info']['name']}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate group report: {str(e)}")

@router.post("/export/all-students")
def export_all_students_report(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Экспорт PDF отчета по всем доступным студентам"""
    
    # Проверка прав доступа
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        # Получаем данные всех студентов (дублируем логику из get_all_students_analytics)
        students_query = db.query(UserInDB).filter(UserInDB.role == "student", UserInDB.is_active == True)
        
        # Фильтрация по ролям
        if current_user.role == "teacher":
            teacher_groups = db.query(Group.id).filter(Group.teacher_id == current_user.id).subquery()
            teacher_courses = db.query(Course.id).filter(Course.teacher_id == current_user.id).subquery()
            
            group_students = db.query(GroupStudent.student_id).filter(GroupStudent.group_id.in_(teacher_groups)).subquery()
            course_students = db.query(Enrollment.user_id).filter(Enrollment.course_id.in_(teacher_courses)).subquery()
            
            students_query = students_query.filter(
                or_(
                    UserInDB.id.in_(group_students),
                    UserInDB.id.in_(course_students)
                )
            )
        
        elif current_user.role == "curator":
            curator_groups = db.query(Group.id).filter(Group.curator_id == current_user.id).subquery()
            group_students = db.query(GroupStudent.student_id).filter(GroupStudent.group_id.in_(curator_groups)).subquery()
            
            students_query = students_query.filter(UserInDB.id.in_(group_students))
        
        students = students_query.all()
        
        students_analytics = []
        for student in students:
            # Получаем группы студента
            student_groups = db.query(Group).join(GroupStudent).filter(
                GroupStudent.student_id == student.id
            ).all()
            
            # Получаем ВСЕ курсы где есть прогресс студента (не через Enrollment!)
            # Используем StepProgress чтобы найти курсы где студент действительно учится
            courses_with_progress = db.query(Course).join(
                Module, Module.course_id == Course.id
            ).join(
                Lesson, Lesson.module_id == Module.id
            ).join(
                Step, Step.lesson_id == Lesson.id
            ).join(
                StepProgress, StepProgress.step_id == Step.id
            ).filter(
                StepProgress.user_id == student.id
            ).distinct().all()
            
            # Если нет прогресса, пробуем через Enrollment
            if not courses_with_progress:
                courses_with_progress = db.query(Course).join(Enrollment).filter(
                    Enrollment.user_id == student.id,
                    Course.is_active == True
                ).all()
            
            active_courses = courses_with_progress
            
            # Подсчитываем общий прогресс
            total_steps = 0
            completed_steps = 0
            total_assignments = 0
            completed_assignments = 0
            total_assignment_score = 0
            total_max_score = 0
            
            for course in active_courses:
                # Подсчет шагов
                course_steps = db.query(Step).join(Lesson).join(Module).filter(
                    Module.course_id == course.id
                ).count()
                total_steps += course_steps
                
                # Правильный подсчет завершенных шагов через JOIN (как в детальном прогрессе)
                course_completed_steps = db.query(StepProgress).join(
                    Step, StepProgress.step_id == Step.id
                ).join(
                    Lesson, Step.lesson_id == Lesson.id
                ).join(
                    Module, Lesson.module_id == Module.id
                ).filter(
                    StepProgress.user_id == student.id,
                    Module.course_id == course.id,
                    StepProgress.status == "completed"
                ).count()
                completed_steps += course_completed_steps
                
                # Подсчет заданий
                course_assignments = db.query(Assignment).join(Lesson).join(Module).filter(
                    Module.course_id == course.id
                ).all()
                total_assignments += len(course_assignments)
                
                for assignment in course_assignments:
                    submission = db.query(AssignmentSubmission).filter(
                        AssignmentSubmission.assignment_id == assignment.id,
                        AssignmentSubmission.user_id == student.id
                    ).first()
                    
                    if submission and submission.is_graded:
                        completed_assignments += 1
                        total_assignment_score += submission.score or 0
                        total_max_score += assignment.max_score or 0
            
            # Вычисляем проценты
            completion_percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
            assignment_score_percentage = (total_assignment_score / total_max_score * 100) if total_max_score > 0 else 0
            
            students_analytics.append({
                "student_id": student.id,
                "student_name": student.name,
                "student_email": student.email,
                "student_number": student.student_id,
                "groups": [{"id": g.id, "name": g.name} for g in student_groups],
                "active_courses_count": len(active_courses),
                "total_steps": total_steps,
                "completed_steps": completed_steps,
                "completion_percentage": round(completion_percentage, 1),
                "total_assignments": total_assignments,
                "completed_assignments": completed_assignments,
                "assignment_score_percentage": round(assignment_score_percentage, 1),
                "total_study_time_minutes": student.total_study_time_minutes,
                "daily_streak": student.daily_streak,
                "last_activity_date": student.last_activity_date
            })
        
        all_students_data = {
            "students": students_analytics,
            "total_students": len(students_analytics)
        }
        
        # Debug logging
        print(f"DEBUG: Total students found: {len(students_analytics)}")
        print(f"DEBUG: Students data: {students_analytics[:2] if students_analytics else 'No students'}")
        
        # Проверяем, есть ли данные
        if len(students_analytics) == 0:
            # Если нет студентов, возвращаем пустой отчет с сообщением
            report_text = f"""
NO STUDENTS FOUND

Your role: {current_user.role}
User ID: {current_user.id}

No students are accessible with your current permissions.

Report generated: {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
            return Response(
                content=report_text.encode('utf-8'),
                media_type="text/plain",
                headers={"Content-Disposition": f"attachment; filename=no_students_{datetime.now().strftime('%Y%m%d')}.txt"}
            )
        
        # Генерируем PDF отчет
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.lib import colors
            
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            
            # Title (English to avoid Cyrillic encoding issues)
            story.append(Paragraph("All Students Report", styles['Title']))
            story.append(Spacer(1, 12))
            
            # Overall Statistics
            total_students = all_students_data['total_students']
            avg_completion = sum(s['completion_percentage'] for s in all_students_data['students']) / total_students if total_students > 0 else 0
            total_study_time = sum(s['total_study_time_minutes'] for s in all_students_data['students'])
            
            summary_info = [
                ['Total Students:', str(total_students)],
                ['Average Progress:', f"{avg_completion:.1f}%"],
                ['Total Study Time:', f"{total_study_time} min ({total_study_time//60} h)"],
            ]
            
            summary_table = Table(summary_info, colWidths=[2*inch, 3*inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.lightblue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
            ]))
            
            story.append(Paragraph("Overall Statistics", styles['Heading2']))
            story.append(summary_table)
            story.append(Spacer(1, 12))
            
            # Students Table
            if all_students_data['students']:
                story.append(Paragraph("Detailed Student Information", styles['Heading2']))
                
                student_data = [['Name', 'Groups', 'Progress %', 'Courses', 'Time (h)']]
                
                for student in all_students_data['students']:
                    groups_str = ', '.join([g['name'] for g in student['groups']]) if student['groups'] else 'No group'
                    student_data.append([
                        student['student_name'],
                        groups_str[:20] + '...' if len(groups_str) > 20 else groups_str,
                        f"{student['completion_percentage']}%",
                        str(student['active_courses_count']),
                        str(student['total_study_time_minutes'] // 60)
                    ])
                
                students_table = Table(student_data, colWidths=[1.5*inch, 1.5*inch, 1*inch, 0.8*inch, 1*inch])
                students_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                
                story.append(students_table)
            
            story.append(Spacer(1, 12))
            story.append(Paragraph(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
            
            doc.build(story)
            buffer.seek(0)
            pdf_content = buffer.getvalue()
            
        except ImportError:
            # Fallback to text report
            report_text = f"""
ALL STUDENTS REPORT

OVERALL STATISTICS:
- Total Students: {all_students_data['total_students']}
- Average Progress: {sum(s['completion_percentage'] for s in all_students_data['students']) / all_students_data['total_students'] if all_students_data['total_students'] > 0 else 0:.1f}%
- Total Study Time: {sum(s['total_study_time_minutes'] for s in all_students_data['students'])} min

STUDENTS:
"""
            for student in all_students_data['students']:
                groups_str = ', '.join([g['name'] for g in student['groups']]) if student['groups'] else 'No group'
                report_text += f"""
- {student['student_name']} ({student['student_email']})
  Groups: {groups_str}
  Progress: {student['completion_percentage']}%
  Active Courses: {student['active_courses_count']}
  Study Time: {student['total_study_time_minutes']} min
"""
            
            report_text += f"\nReport generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            pdf_content = report_text.encode('utf-8')
        
        filename = f"all_students_report_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate all students report: {str(e)}")

# =============================================================================
# DETAILED STEP-BY-STEP PROGRESS TRACKING
# =============================================================================

@router.get("/student/{student_id}/detailed-progress")
def get_student_detailed_progress(
    student_id: int,
    course_id: Optional[int] = None,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Получить детальный прогресс студента по шагам
    Показывает каждый шаг, время прохождения, порядок выполнения
    """
    
    # Проверка прав доступа
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Проверяем доступ к студенту
    if current_user.role != "admin" and not check_student_access(student_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this student")
    
    try:
        # Получаем информацию о студенте
        student = db.query(UserInDB).filter(UserInDB.id == student_id).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        
        # Базовый запрос для прогресса по шагам
        query = db.query(
            StepProgress,
            Step,
            Lesson,
            Module,
            Course
        ).join(Step, StepProgress.step_id == Step.id)\
         .join(Lesson, Step.lesson_id == Lesson.id)\
         .join(Module, Lesson.module_id == Module.id)\
         .join(Course, Module.course_id == Course.id)\
         .filter(StepProgress.user_id == student_id)
        
        if course_id:
            query = query.filter(Course.id == course_id)
        
        # Получаем все записи прогресса
        progress_records = query.order_by(StepProgress.visited_at.desc()).all()
        
        # Группируем по курсам
        courses_progress = {}
        
        for step_progress, step, lesson, module, course in progress_records:
            course_key = course.id
            
            if course_key not in courses_progress:
                courses_progress[course_key] = {
                    "course_info": {
                        "id": course.id,
                        "title": course.title,
                        "description": course.description
                    },
                    "modules": {}
                }
            
            module_key = module.id
            if module_key not in courses_progress[course_key]["modules"]:
                courses_progress[course_key]["modules"][module_key] = {
                    "module_info": {
                        "id": module.id,
                        "title": module.title,
                        "order_index": module.order_index
                    },
                    "lessons": {}
                }
            
            lesson_key = lesson.id
            if lesson_key not in courses_progress[course_key]["modules"][module_key]["lessons"]:
                courses_progress[course_key]["modules"][module_key]["lessons"][lesson_key] = {
                    "lesson_info": {
                        "id": lesson.id,
                        "title": lesson.title,
                        "order_index": lesson.order_index
                    },
                    "steps": []
                }
            
            # Добавляем информацию о шаге
            step_info = {
                "step_id": step.id,
                "step_title": step.title,
                "step_order": step.order_index,
                "content_type": step.content_type,
                "progress": {
                    "status": step_progress.status,
                    "started_at": step_progress.started_at.isoformat() if step_progress.started_at else None,
                    "visited_at": step_progress.visited_at.isoformat() if step_progress.visited_at else None,
                    "completed_at": step_progress.completed_at.isoformat() if step_progress.completed_at else None,
                    "time_spent_minutes": step_progress.time_spent_minutes,
                    "attempts": 1  # Можно расширить для отслеживания попыток
                }
            }
            
            courses_progress[course_key]["modules"][module_key]["lessons"][lesson_key]["steps"].append(step_info)
        
        # Получаем общую статистику
        total_steps_query = db.query(func.count(Step.id)).join(Lesson).join(Module)
        completed_steps_query = db.query(func.count(StepProgress.id)).join(Step).join(Lesson).join(Module).filter(
            StepProgress.user_id == student_id,
            StepProgress.status == 'completed'
        )
        
        if course_id:
            total_steps_query = total_steps_query.filter(Module.course_id == course_id)
            completed_steps_query = completed_steps_query.filter(Module.course_id == course_id)
        
        total_steps = total_steps_query.scalar() or 0
        completed_steps = completed_steps_query.scalar() or 0
        
        # Получаем временную статистику
        first_activity = db.query(func.min(StepProgress.visited_at)).filter(
            StepProgress.user_id == student_id
        ).scalar()
        
        last_activity = db.query(func.max(StepProgress.visited_at)).filter(
            StepProgress.user_id == student_id
        ).scalar()
        
        total_study_time = db.query(func.sum(StepProgress.time_spent_minutes)).filter(
            StepProgress.user_id == student_id
        ).scalar() or 0
        
        # Получаем активность по дням (последние 30 дней)
        from datetime import datetime, timedelta
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        daily_activity = db.query(
            func.date(StepProgress.visited_at).label('date'),
            func.count(StepProgress.id).label('steps_completed'),
            func.sum(StepProgress.time_spent_minutes).label('time_spent')
        ).filter(
            StepProgress.user_id == student_id,
            StepProgress.visited_at >= thirty_days_ago
        ).group_by(func.date(StepProgress.visited_at)).all()
        
        return {
            "student_info": {
                "id": student.id,
                "name": student.name,
                "email": student.email,
                "student_id": getattr(student, 'student_id', None)
            },
            "summary": {
                "total_steps": total_steps,
                "completed_steps": completed_steps,
                "completion_percentage": (completed_steps / total_steps * 100) if total_steps > 0 else 0,
                "total_study_time_minutes": total_study_time,
                "first_activity": first_activity.isoformat() if first_activity else None,
                "last_activity": last_activity.isoformat() if last_activity else None,
                "study_period_days": (last_activity - first_activity).days if first_activity and last_activity else 0
            },
            "daily_activity": [
                {
                    "date": activity.date.isoformat(),
                    "steps_completed": activity.steps_completed,
                    "time_spent_minutes": activity.time_spent or 0
                }
                for activity in daily_activity
            ],
            "courses_progress": courses_progress
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get detailed progress: {str(e)}")

@router.get("/student/{student_id}/learning-path")
def get_student_learning_path(
    student_id: int,
    course_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Получить путь обучения студента - хронологический порядок прохождения шагов
    """
    
    # Проверка прав доступа
    if current_user.role not in ["teacher", "curator", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role != "admin" and not check_student_access(student_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this student")
    
    try:
        # Получаем хронологический путь обучения
        learning_path = db.query(
            StepProgress,
            Step,
            Lesson,
            Module
        ).join(Step, StepProgress.step_id == Step.id)\
         .join(Lesson, Step.lesson_id == Lesson.id)\
         .join(Module, Lesson.module_id == Module.id)\
         .filter(
            StepProgress.user_id == student_id,
            Module.course_id == course_id
        ).order_by(StepProgress.visited_at.asc()).all()
        
        path_data = []
        for i, (step_progress, step, lesson, module) in enumerate(learning_path):
            # Вычисляем время между шагами
            time_since_previous = None
            if i > 0 and learning_path[i-1][0].visited_at and step_progress.visited_at:
                time_diff = step_progress.visited_at - learning_path[i-1][0].visited_at
                time_since_previous = int(time_diff.total_seconds() / 60)  # в минутах
            
            path_data.append({
                "sequence_number": i + 1,
                "step_info": {
                    "id": step.id,
                    "title": step.title,
                    "content_type": step.content_type,
                    "order_index": step.order_index
                },
                "lesson_info": {
                    "id": lesson.id,
                    "title": lesson.title,
                    "order_index": lesson.order_index
                },
                "module_info": {
                    "id": module.id,
                    "title": module.title,
                    "order_index": module.order_index
                },
                "progress_info": {
                    "visited_at": step_progress.visited_at.isoformat() if step_progress.visited_at else None,
                    "completed_at": step_progress.completed_at.isoformat() if step_progress.completed_at else None,
                    "time_spent_minutes": step_progress.time_spent_minutes,
                    "status": step_progress.status,
                    "time_since_previous_step_minutes": time_since_previous
                }
            })
        
        return {
            "student_id": student_id,
            "course_id": course_id,
            "total_steps_completed": len(path_data),
            "learning_path": path_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get learning path: {str(e)}")
