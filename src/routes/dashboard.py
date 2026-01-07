from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from typing import List, Optional
from datetime import datetime, timedelta
import json

from src.config import get_db
from src.schemas.models import (
    UserInDB, Course, Module, Lesson, Enrollment, StudentProgress,
    DashboardStatsSchema, CourseProgressSchema, UserSchema, Step, StepProgress
)
from src.routes.auth import get_current_user_dependency
from src.utils.permissions import require_role
from src.schemas.models import GroupStudent

router = APIRouter()

@router.get("/stats", response_model=DashboardStatsSchema)
async def get_dashboard_stats(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get dashboard statistics for current user
    Supports different views based on user role
    """
    if current_user.role == "student":
        return get_student_dashboard_stats(current_user, db)
    elif current_user.role == "teacher":
        return get_teacher_dashboard_stats(current_user, db)
    elif current_user.role == "curator":
        return get_curator_dashboard_stats(current_user, db)
    elif current_user.role == "admin":
        return get_admin_dashboard_stats(current_user, db)
    else:
        raise HTTPException(status_code=403, detail="Invalid user role")

def get_student_dashboard_stats(user: UserInDB, db: Session) -> DashboardStatsSchema:
    """Get dashboard stats for student"""
    # Get student's active enrollments
    enrollments = db.query(Enrollment).filter(
        Enrollment.user_id == user.id,
        Enrollment.is_active == True
    ).all()
    
    # Get group access courses
    from src.schemas.models import GroupStudent, CourseGroupAccess
    
    group_student = db.query(GroupStudent).filter(
        GroupStudent.student_id == user.id
    ).first()
    
    group_courses = []
    if group_student:
        group_access = db.query(CourseGroupAccess).filter(
            CourseGroupAccess.group_id == group_student.group_id,
            CourseGroupAccess.is_active == True
        ).all()
        
        for access in group_access:
            course = db.query(Course).filter(
                Course.id == access.course_id,
                Course.is_active == True
            ).first()
            if course:
                group_courses.append(course)
    
    # Combine both sets of courses (enrollment + group access)
    all_courses = []
    
    # Add enrollment courses
    for enrollment in enrollments:
        course = db.query(Course).filter(
            Course.id == enrollment.course_id,
            Course.is_active == True
        ).first()
        if course:
            all_courses.append(course)
    
    # Add group access courses (avoid duplicates)
    enrollment_course_ids = [e.course_id for e in enrollments]
    for course in group_courses:
        if course.id not in enrollment_course_ids:
            all_courses.append(course)
    
    enrolled_courses_count = len(all_courses)
    
    # Calculate total study time (convert minutes to hours)
    total_study_time_hours = (user.total_study_time_minutes or 0) // 60
    
    # Calculate average progress across all courses using StepProgress
    total_progress = 0
    course_progresses = []
    
    for course in all_courses:
        # Get all steps in this course
        total_steps = db.query(Step).join(Lesson).join(Module).filter(
            Module.course_id == course.id
        ).count()
        
        # Get completed steps for this user in this course
        completed_steps = db.query(StepProgress).filter(
            StepProgress.user_id == user.id,
            StepProgress.course_id == course.id,
            StepProgress.status == "completed"
        ).count()
        
        # Calculate progress percentage
        if total_steps > 0:
            course_avg_progress = (completed_steps / total_steps) * 100
        else:
            course_avg_progress = 0
        
        total_progress += course_avg_progress
        
        # Get teacher info
        teacher = db.query(UserInDB).filter(UserInDB.id == course.teacher_id).first()
        teacher_name = teacher.name if teacher else "Unknown Teacher"
        
        # Count total modules in course
        total_modules = db.query(Module).filter(Module.course_id == course.id).count()
        
        # Get last accessed time from StepProgress
        last_step_progress = db.query(StepProgress).filter(
            StepProgress.user_id == user.id,
            StepProgress.course_id == course.id
        ).order_by(desc(StepProgress.visited_at)).first()
        
        course_progresses.append({
            "id": course.id,
            "title": course.title,
            "cover_image": course.cover_image_url,
            "teacher": teacher_name,
            "total_modules": total_modules,
            "progress": round(course_avg_progress),
            "status": "completed" if course_avg_progress >= 100 else "in_progress" if course_avg_progress > 0 else "not_started",
            "last_accessed": last_step_progress.visited_at if (last_step_progress and last_step_progress.visited_at) else None
        })
    
    # Calculate overall average progress
    average_progress = round(total_progress / enrolled_courses_count) if enrolled_courses_count > 0 else 0
    
    # Sort courses by last accessed (most recent first), handling None values
    # Courses with None last_accessed (never accessed) will be placed at the end
    course_progresses.sort(
        key=lambda x: x["last_accessed"] if x["last_accessed"] is not None else datetime.min, 
        reverse=True
    )
    
    return DashboardStatsSchema(
        user={
            "name": user.name.split()[0],  # First name only like "Fikrat"
            "full_name": user.name,
            "role": user.role,
            "avatar_url": user.avatar_url
        },
        stats={
            "enrolled_courses": enrolled_courses_count,
            "total_study_time_hours": total_study_time_hours,
            "average_progress": average_progress
        },
        recent_courses=course_progresses[:6]  # Limit to 6 recent courses
    )

def get_teacher_dashboard_stats(user: UserInDB, db: Session) -> DashboardStatsSchema:
    """Get dashboard stats for teacher"""
    from src.schemas.models import Assignment, AssignmentSubmission, CourseGroupAccess, Group
    
    # Get teacher's groups (groups where this teacher is the owner)
    teacher_groups = db.query(Group).filter(
        Group.teacher_id == user.id,
        Group.is_active == True
    ).all()
    
    teacher_group_ids = [g.id for g in teacher_groups] if teacher_groups else []
    
    # Get students from teacher's groups
    student_ids_set = set()
    if teacher_group_ids:
        group_students = db.query(GroupStudent).filter(
            GroupStudent.group_id.in_(teacher_group_ids)
        ).all()
        for gs in group_students:
            student_ids_set.add(gs.student_id)
    
    total_students = len(student_ids_set)
    
    # Get courses that have access for teacher's groups
    course_ids_with_access = []
    if teacher_group_ids:
        course_ids_with_access = db.query(CourseGroupAccess.course_id).filter(
            CourseGroupAccess.group_id.in_(teacher_group_ids),
            CourseGroupAccess.is_active == True
        ).distinct().all()
        course_ids_with_access = [c[0] for c in course_ids_with_access]
    
    # Get those courses
    teacher_courses = db.query(Course).filter(
        Course.id.in_(course_ids_with_access),
        Course.is_active == True
    ).all() if course_ids_with_access else []
    
    total_courses = len(teacher_courses)
    
    # Get active students (accessed lessons in last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    active_students = 0
    
    if teacher_courses and student_ids_set:
        active_students = db.query(func.count(func.distinct(StudentProgress.user_id))).filter(
            StudentProgress.course_id.in_([c.id for c in teacher_courses]),
            StudentProgress.user_id.in_(student_ids_set),
            StudentProgress.last_accessed >= seven_days_ago
        ).scalar() or 0
    
    # Calculate average student progress across all students
    avg_student_progress = 0
    if teacher_courses and student_ids_set:
        progress_records = db.query(StudentProgress).filter(
            StudentProgress.course_id.in_([c.id for c in teacher_courses]),
            StudentProgress.user_id.in_(student_ids_set)
        ).all()
        
        if progress_records:
            total_progress = sum(p.completion_percentage for p in progress_records)
            avg_student_progress = round(total_progress / len(progress_records))
    
    # Get pending submissions (ungraded)
    pending_submissions = 0
    total_submissions = 0
    graded_submissions_list = []
    avg_student_score = 0
    
    if teacher_courses:
        teacher_assignments = db.query(Assignment).filter(
            Assignment.lesson_id.in_(
                db.query(Lesson.id).filter(
                    Lesson.module_id.in_(
                        db.query(Module.id).filter(
                            Module.course_id.in_([c.id for c in teacher_courses])
                        )
                    )
                )
            ),
            Assignment.is_active == True
        ).all()
        
        if teacher_assignments:
            pending_submissions = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.assignment_id.in_([a.id for a in teacher_assignments]),
                AssignmentSubmission.is_graded == False
            ).count()
            
            total_submissions = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.assignment_id.in_([a.id for a in teacher_assignments])
            ).count()
            
            graded_submissions_list = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.assignment_id.in_([a.id for a in teacher_assignments]),
                AssignmentSubmission.is_graded == True,
                AssignmentSubmission.score.isnot(None)
            ).all()
            
            # Calculate average student score
            if graded_submissions_list:
                total_score = sum(sub.score for sub in graded_submissions_list if sub.score is not None)
                avg_student_score = round(total_score / len(graded_submissions_list))
    
    # Get recent enrollments (last 7 days)
    recent_enrollments = 0
    if teacher_courses:
        recent_enrollments = db.query(Enrollment).filter(
            Enrollment.course_id.in_([c.id for c in teacher_courses]),
            Enrollment.enrolled_at >= seven_days_ago,
            Enrollment.is_active == True
        ).count()
    
    # Calculate average completion rate
    total_completion_rate = 0
    
    course_stats = []
    
    for course in teacher_courses:
        # Count enrolled students for this course (for course_stats only, not total_students)
        enrolled_students = db.query(Enrollment).filter(
            Enrollment.course_id == course.id,
            Enrollment.is_active == True
        ).count()
        
        # Also add students from group access for this course
        group_accesses = db.query(CourseGroupAccess).filter(
            CourseGroupAccess.course_id == course.id,
            CourseGroupAccess.is_active == True
        ).all()
        
        course_group_students = 0
        for access in group_accesses:
            course_group_students += db.query(GroupStudent).filter(
                GroupStudent.group_id == access.group_id
            ).count()
        
        total_course_students = enrolled_students + course_group_students
        
        # Count modules
        total_modules = db.query(Module).filter(Module.course_id == course.id).count()
        
        # Calculate average progress for this course
        progress_records = db.query(StudentProgress).filter(
            StudentProgress.course_id == course.id
        ).all()
        
        if progress_records:
            avg_progress = sum(p.completion_percentage for p in progress_records) / len(progress_records)
            total_completion_rate += avg_progress
        else:
            avg_progress = 0
        
        # Get course completion rate
        course_completion_rate = 0
        if total_course_students > 0 and progress_records:
            # Calculate percentage of students who completed the course
            completed_count = sum(1 for p in progress_records if p.completion_percentage >= 100)
            course_completion_rate = round((completed_count / total_course_students) * 100)
        
        course_stats.append({
            "id": course.id,
            "title": course.title,
            "cover_image": course.cover_image_url,
            "teacher": user.name,
            "total_modules": total_modules,
            "enrolled_students": total_course_students,
            "completion_rate": course_completion_rate,
            "progress": round(avg_progress),
            "status": "active",
            "last_accessed": course.updated_at
        })
    
    # Calculate average completion rate
    avg_completion_rate = round(total_completion_rate / total_courses) if total_courses > 0 else 0
    
    # Ensure all values are numeric
    graded_submissions_count = len(graded_submissions_list) if graded_submissions_list else 0
    grading_progress = round((graded_submissions_count / total_submissions) * 100) if total_submissions > 0 else 0
    
    return DashboardStatsSchema(
        user={
            "name": user.name.split()[0],
            "full_name": user.name,
            "role": user.role,
            "avatar_url": user.avatar_url
        },
        stats={
            "total_courses": total_courses,
            "total_students": total_students,
            "active_students": active_students,
            "avg_student_progress": avg_student_progress,
            "pending_submissions": pending_submissions,
            "recent_enrollments": recent_enrollments,
            "avg_completion_rate": avg_completion_rate,
            "avg_student_score": avg_student_score,
            "total_submissions": total_submissions,
            "graded_submissions": graded_submissions_count,
            "grading_progress": grading_progress
        },
        recent_courses=course_stats[:6]
    )

def get_curator_dashboard_stats(user: UserInDB, db: Session) -> DashboardStatsSchema:
    """Get dashboard stats for curator"""
    # Get groups where current user is curator
    from src.schemas.models import Group
    curator_groups = db.query(Group).filter(
        Group.curator_id == user.id
    ).all()
    
    # Get students assigned to curator (from curator's groups)
    assigned_students = []
    if curator_groups:
        group_ids = [group.id for group in curator_groups]
        # Get students in curator's groups using GroupStudent association table
        group_student_ids = db.query(GroupStudent.student_id).filter(
            GroupStudent.group_id.in_(group_ids)
        ).subquery()
        assigned_students = db.query(UserInDB).filter(
            UserInDB.role == "student",
            UserInDB.id.in_(group_student_ids),
            UserInDB.is_active == True
        ).all()
    
    total_students = len(assigned_students)
    
    # Calculate stats for assigned students
    total_courses_monitored = 0
    students_with_progress = []
    
    for student in assigned_students:
        enrollments = db.query(Enrollment).filter(
            Enrollment.user_id == student.id,
            Enrollment.is_active == True
        ).count()
        total_courses_monitored += enrollments
        
        # Get average progress for student
        progress_records = db.query(StudentProgress).filter(
            StudentProgress.user_id == student.id
        ).all()
        
        if progress_records:
            avg_progress = sum(p.completion_percentage for p in progress_records) / len(progress_records)
        else:
            avg_progress = 0
        
        students_with_progress.append({
            "id": student.id,
            "name": student.name,
            "student_id": student.student_id,
            "progress": round(avg_progress),
            "total_courses": enrollments,
            "last_activity": max([p.last_accessed for p in progress_records]) if progress_records else None
        })
    
    return DashboardStatsSchema(
        user={
            "name": user.name.split()[0],
            "full_name": user.name,
            "role": user.role,
            "avatar_url": user.avatar_url
        },
        stats={
            "assigned_students": total_students,
            "total_courses_monitored": total_courses_monitored,
            "average_student_progress": round(sum(s["progress"] for s in students_with_progress) / len(students_with_progress)) if students_with_progress else 0
        },
        recent_courses=students_with_progress[:6]  # Show recent student activity instead of courses
    )

def get_admin_dashboard_stats(user: UserInDB, db: Session) -> DashboardStatsSchema:
    """Get dashboard stats for admin"""
    # Get platform-wide statistics
    total_users = db.query(UserInDB).filter(UserInDB.is_active == True).count()
    total_students = db.query(UserInDB).filter(
        UserInDB.role == "student",
        UserInDB.is_active == True
    ).count()
    total_teachers = db.query(UserInDB).filter(
        UserInDB.role == "teacher",
        UserInDB.is_active == True
    ).count()
    total_courses = db.query(Course).filter(Course.is_active == True).count()
    total_enrollments = db.query(Enrollment).filter(Enrollment.is_active == True).count()
    
    # Get recent course activity
    recent_courses = db.query(Course).filter(
        Course.is_active == True
    ).order_by(desc(Course.updated_at)).limit(6).all()
    
    course_list = []
    for course in recent_courses:
        teacher = db.query(UserInDB).filter(UserInDB.id == course.teacher_id).first()
        enrolled_count = db.query(Enrollment).filter(
            Enrollment.course_id == course.id,
            Enrollment.is_active == True
        ).count()
        
        course_list.append({
            "id": course.id,
            "title": course.title,
            "cover_image": course.cover_image_url,
            "teacher": teacher.name if teacher else "Unknown",
            "enrolled_students": enrolled_count,
            "status": "active",
            "last_accessed": course.updated_at
        })
    
    return DashboardStatsSchema(
        user={
            "name": user.name.split()[0],
            "full_name": user.name,
            "role": user.role,
            "avatar_url": user.avatar_url
        },
        stats={
            "total_users": total_users,
            "total_students": total_students,
            "total_teachers": total_teachers,
            "total_courses": total_courses,
            "total_enrollments": total_enrollments
        },
        recent_courses=course_list
    )

@router.get("/my-courses", response_model=List[CourseProgressSchema])
async def get_my_courses(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get detailed list of user's courses with progress"""
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can access this endpoint")
    
    # Get student's enrollments
    enrollments = db.query(Enrollment).filter(
        Enrollment.user_id == current_user.id,
        Enrollment.is_active == True
    ).all()
    
    # Get group access courses
    from src.schemas.models import GroupStudent, CourseGroupAccess
    
    group_student = db.query(GroupStudent).filter(
        GroupStudent.student_id == current_user.id
    ).first()
    
    group_courses = []
    if group_student:
        group_access = db.query(CourseGroupAccess).filter(
            CourseGroupAccess.group_id == group_student.group_id,
            CourseGroupAccess.is_active == True
        ).all()
        
        for access in group_access:
            course = db.query(Course).filter(
                Course.id == access.course_id,
                Course.is_active == True
            ).first()
            if course:
                group_courses.append(course)
    
    # Combine both sets of courses (enrollment + group access)
    all_courses = []
    
    # Add enrollment courses
    for enrollment in enrollments:
        course = db.query(Course).filter(
            Course.id == enrollment.course_id,
            Course.is_active == True
        ).first()
        if course:
            all_courses.append(course)
    
    # Add group access courses (avoid duplicates)
    enrollment_course_ids = [e.course_id for e in enrollments]
    for course in group_courses:
        if course.id not in enrollment_course_ids:
            all_courses.append(course)
    
    courses_with_progress = []
    
    for course in all_courses:
        # Get teacher info
        teacher = db.query(UserInDB).filter(UserInDB.id == course.teacher_id).first()
        teacher_name = teacher.name if teacher else "Unknown Teacher"
        
        # Count total modules
        total_modules = db.query(Module).filter(Module.course_id == course.id).count()
        
        # Calculate progress
        progress_records = db.query(StudentProgress).filter(
            StudentProgress.user_id == current_user.id,
            StudentProgress.course_id == course.id
        ).all()
        
        if progress_records:
            completion_percentage = round(sum(p.completion_percentage for p in progress_records) / len(progress_records))
            last_accessed = max(p.last_accessed for p in progress_records)
        else:
            completion_percentage = 0
            # Use current time for group access courses that haven't been accessed yet
            last_accessed = datetime.utcnow()
        
        # Determine status
        if completion_percentage >= 100:
            status = "completed"
        elif completion_percentage > 0:
            status = "in_progress"
        else:
            status = "not_started"
        
        courses_with_progress.append(CourseProgressSchema(
            course_id=course.id,
            course_title=course.title,
            teacher_name=teacher_name,
            cover_image_url=course.cover_image_url,
            total_modules=total_modules,
            completion_percentage=completion_percentage,
            status=status,
            last_accessed=last_accessed
        ))
    
    # Sort by last accessed (most recent first)
    courses_with_progress.sort(key=lambda x: x.last_accessed or datetime.min, reverse=True)
    
    return courses_with_progress

@router.get("/recent-activity")
async def get_recent_activity(
    limit: int = 10,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get recent learning activity for current user"""
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can access this endpoint")
    
    # Get recent progress records
    recent_progress = db.query(StudentProgress).filter(
        StudentProgress.user_id == current_user.id
    ).order_by(desc(StudentProgress.last_accessed)).limit(limit).all()
    
    activities = []
    
    for progress in recent_progress:
        course = db.query(Course).filter(Course.id == progress.course_id).first()
        lesson = db.query(Lesson).filter(Lesson.id == progress.lesson_id).first() if progress.lesson_id else None
        
        activity = {
            "id": progress.id,
            "type": "lesson" if lesson else "course",
            "course_title": course.title if course else "Unknown Course",
            "lesson_title": lesson.title if lesson else None,
            "progress": progress.completion_percentage,
            "status": progress.status,
            "time_spent": progress.time_spent_minutes,
            "last_accessed": progress.last_accessed
        }
        activities.append(activity)
    
    return {"recent_activities": activities}

@router.post("/update-study-time")
async def update_study_time(
    minutes_studied: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Update user's total study time"""
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can update study time")
    
    current_user.total_study_time_minutes += minutes_studied
    db.commit()
    
    return {
        "detail": "Study time updated successfully",
        "total_study_time_minutes": current_user.total_study_time_minutes,
        "total_study_time_hours": current_user.total_study_time_minutes // 60
    }

@router.get("/teacher/pending-submissions")
async def get_teacher_pending_submissions(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get pending submissions for teacher's students (from teacher's groups)"""
    if current_user.role not in ["teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only teachers can access this endpoint")
    
    from src.schemas.models import Assignment, AssignmentSubmission, CourseGroupAccess, Group
    
    # Get teacher's groups
    teacher_groups = db.query(Group).filter(
        Group.teacher_id == current_user.id,
        Group.is_active == True
    ).all()
    
    if not teacher_groups:
        return {"pending_submissions": []}
    
    teacher_group_ids = [g.id for g in teacher_groups]
    
    # Get students from teacher's groups
    teacher_student_ids = set()
    group_students = db.query(GroupStudent).filter(
        GroupStudent.group_id.in_(teacher_group_ids)
    ).all()
    for gs in group_students:
        teacher_student_ids.add(gs.student_id)
    
    if not teacher_student_ids:
        return {"pending_submissions": []}
    
    # Get courses that teacher's groups have access to
    course_ids = db.query(CourseGroupAccess.course_id).filter(
        CourseGroupAccess.group_id.in_(teacher_group_ids),
        CourseGroupAccess.is_active == True
    ).distinct().all()
    course_ids = [c[0] for c in course_ids]
    
    if not course_ids:
        return {"pending_submissions": []}
    
    # Get assignments from those courses
    teacher_assignments = db.query(Assignment).filter(
        Assignment.lesson_id.in_(
            db.query(Lesson.id).filter(
                Lesson.module_id.in_(
                    db.query(Module.id).filter(
                        Module.course_id.in_(course_ids)
                    )
                )
            )
        ),
        Assignment.is_active == True
    ).all()
    
    # Add assignments directly linked to groups
    group_assignments = db.query(Assignment).filter(
        Assignment.group_id.in_(teacher_group_ids),
        Assignment.is_active == True
    ).all()
    teacher_assignments.extend(group_assignments)

    if not teacher_assignments:
        return {"pending_submissions": []}
    
    # Get pending submissions ONLY from teacher's students
    pending_submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id.in_([a.id for a in teacher_assignments]),
        AssignmentSubmission.user_id.in_(teacher_student_ids),
        AssignmentSubmission.is_graded == False
    ).all()
    
    submissions_data = []
    for submission in pending_submissions:
        # Get assignment details
        assignment = db.query(Assignment).filter(Assignment.id == submission.assignment_id).first()
        
        # Get student details
        student = db.query(UserInDB).filter(UserInDB.id == submission.user_id).first()
        
        # Get course details
        course = None
        if assignment and assignment.lesson_id:
            lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
            if lesson:
                module = db.query(Module).filter(Module.id == lesson.module_id).first()
                if module:
                    course = db.query(Course).filter(Course.id == module.course_id).first()
        
        submissions_data.append({
            "id": submission.id,
            "assignment_id": submission.assignment_id,
            "assignment_title": assignment.title if assignment else "Unknown Assignment",
            "course_title": course.title if course else "Unknown Course",
            "user_id": submission.user_id,
            "student_name": student.name if student else "Unknown Student",
            "student_email": student.email if student else "",
            "submitted_at": submission.submitted_at,
            "max_score": submission.max_score,
            "file_url": submission.file_url,
            "submitted_file_name": submission.submitted_file_name
        })
    
    # Sort by submission date (most recent first), handling potential None values
    submissions_data.sort(key=lambda x: x["submitted_at"] if x["submitted_at"] is not None else datetime.min, reverse=True)
    
    return {"pending_submissions": submissions_data}

@router.get("/teacher/recent-submissions")
async def get_teacher_recent_submissions(
    limit: int = 10,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get recent submissions for teacher's students (from teacher's groups)"""
    if current_user.role not in ["teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only teachers can access this endpoint")
    
    from src.schemas.models import Assignment, AssignmentSubmission, CourseGroupAccess, Group
    
    # Get teacher's groups
    teacher_groups = db.query(Group).filter(
        Group.teacher_id == current_user.id,
        Group.is_active == True
    ).all()
    
    if not teacher_groups:
        return {"recent_submissions": []}
    
    teacher_group_ids = [g.id for g in teacher_groups]
    
    # Get students from teacher's groups
    teacher_student_ids = set()
    group_students = db.query(GroupStudent).filter(
        GroupStudent.group_id.in_(teacher_group_ids)
    ).all()
    for gs in group_students:
        teacher_student_ids.add(gs.student_id)
    
    if not teacher_student_ids:
        return {"recent_submissions": []}
    
    # Get courses that teacher's groups have access to
    course_ids = db.query(CourseGroupAccess.course_id).filter(
        CourseGroupAccess.group_id.in_(teacher_group_ids),
        CourseGroupAccess.is_active == True
    ).distinct().all()
    course_ids = [c[0] for c in course_ids]
    
    if not course_ids:
        return {"recent_submissions": []}
    
    # Get assignments from those courses
    teacher_assignments = db.query(Assignment).filter(
        Assignment.lesson_id.in_(
            db.query(Lesson.id).filter(
                Lesson.module_id.in_(
                    db.query(Module.id).filter(
                        Module.course_id.in_(course_ids)
                    )
                )
            )
        ),
        Assignment.is_active == True
    ).all()
    
    # Add assignments directly linked to groups
    group_assignments = db.query(Assignment).filter(
        Assignment.group_id.in_(teacher_group_ids),
        Assignment.is_active == True
    ).all()
    teacher_assignments.extend(group_assignments)

    if not teacher_assignments:
        return {"recent_submissions": []}
    
    # Get recent submissions ONLY from teacher's students
    recent_submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id.in_([a.id for a in teacher_assignments]),
        AssignmentSubmission.user_id.in_(teacher_student_ids)
    ).order_by(AssignmentSubmission.submitted_at.desc()).limit(limit).all()
    
    submissions_data = []
    for submission in recent_submissions:
        # Get assignment details
        assignment = db.query(Assignment).filter(Assignment.id == submission.assignment_id).first()
        
        # Get student details
        student = db.query(UserInDB).filter(UserInDB.id == submission.user_id).first()
        
        # Get course details
        course = None
        if assignment and assignment.lesson_id:
            lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
            if lesson:
                module = db.query(Module).filter(Module.id == lesson.module_id).first()
                if module:
                    course = db.query(Course).filter(Course.id == module.course_id).first()
        
        # Get grader details if graded
        grader_name = None
        if submission.graded_by:
            grader = db.query(UserInDB).filter(UserInDB.id == submission.graded_by).first()
            grader_name = grader.name if grader else None
        
        submissions_data.append({
            "id": submission.id,
            "assignment_id": submission.assignment_id,
            "assignment_title": assignment.title if assignment else "Unknown Assignment",
            "course_title": course.title if course else "Unknown Course",
            "user_id": submission.user_id,
            "student_name": student.name if student else "Unknown Student",
            "student_email": student.email if student else "",
            "submitted_at": submission.submitted_at,
            "graded_at": submission.graded_at,
            "score": submission.score,
            "max_score": submission.max_score,
            "is_graded": submission.is_graded,
            "feedback": submission.feedback,
            "grader_name": grader_name,
            "file_url": submission.file_url,
            "submitted_file_name": submission.submitted_file_name
        })
    
    return {"recent_submissions": submissions_data}

@router.get("/teacher/students-progress")
async def get_teacher_students_progress(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get list of students with their current lesson progress for teacher's groups"""
    if current_user.role not in ["teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only teachers can access this endpoint")
    
    from src.schemas.models import CourseGroupAccess, Group
    
    # Get teacher's groups (groups where this teacher is the owner)
    teacher_groups = db.query(Group).filter(
        Group.teacher_id == current_user.id,
        Group.is_active == True
    ).all()
    
    if not teacher_groups:
        return {"students_progress": []}
    
    teacher_group_ids = [g.id for g in teacher_groups]
    teacher_groups_map = {g.id: g for g in teacher_groups}
    
    # Get all students from teacher's groups with their group info
    group_student_records = db.query(GroupStudent).filter(
        GroupStudent.group_id.in_(teacher_group_ids)
    ).all()
    
    if not group_student_records:
        return {"students_progress": []}
    
    students_data = []
    student_ids_seen = set()
    
    # Process each student from teacher's groups
    for gs in group_student_records:
        if gs.student_id in student_ids_seen:
            continue
            
        student = db.query(UserInDB).filter(UserInDB.id == gs.student_id).first()
        if not student:
            continue
        
        group = teacher_groups_map.get(gs.group_id)
        group_name = group.name if group else None
        
        # Get courses that this student's group has access to
        group_course_access = db.query(CourseGroupAccess).filter(
            CourseGroupAccess.group_id == gs.group_id,
            CourseGroupAccess.is_active == True
        ).all()
        
        if not group_course_access:
            # Student has no courses assigned - still show them
            students_data.append({
                "student_id": student.id,
                "student_name": student.name,
                "student_email": student.email,
                "student_avatar": student.avatar_url,
                "group_name": group_name,
                "course_id": None,
                "course_title": "No courses assigned",
                "current_lesson_id": None,
                "current_lesson_title": "Not started",
                "lesson_progress": 0,
                "overall_progress": 0,
                "last_activity": None
            })
            student_ids_seen.add(gs.student_id)
            continue
        
        # For each course the student has access to
        for access in group_course_access:
            course = db.query(Course).filter(
                Course.id == access.course_id,
                Course.is_active == True
            ).first()
            
            if not course:
                continue
            
            # Find last accessed lesson through StepProgress
            last_step_progress = db.query(StepProgress).filter(
                StepProgress.user_id == student.id,
                StepProgress.course_id == course.id
            ).order_by(desc(StepProgress.visited_at)).first()
            
            current_lesson_title = None
            current_lesson_id = None
            lesson_progress_percentage = 0
            
            if last_step_progress:
                # Get the lesson from the step
                step = db.query(Step).filter(Step.id == last_step_progress.step_id).first()
                if step:
                    lesson = db.query(Lesson).filter(Lesson.id == step.lesson_id).first()
                    if lesson:
                        current_lesson_title = lesson.title
                        current_lesson_id = lesson.id
                        
                        # Calculate lesson progress (completed steps / total steps in lesson)
                        lesson_steps = db.query(Step).filter(Step.lesson_id == lesson.id).count()
                        completed_lesson_steps = db.query(StepProgress).filter(
                            StepProgress.user_id == student.id,
                            StepProgress.step_id.in_(
                                db.query(Step.id).filter(Step.lesson_id == lesson.id)
                            ),
                            StepProgress.status == 'completed'
                        ).count()
                        
                        lesson_progress_percentage = round((completed_lesson_steps / lesson_steps) * 100) if lesson_steps > 0 else 0
            
            # Calculate overall course progress and get last activity
            all_progress = db.query(StudentProgress).filter(
                StudentProgress.user_id == student.id,
                StudentProgress.course_id == course.id
            ).all()
            
            overall_progress = 0
            last_activity = None
            
            if all_progress:
                overall_progress = round(sum(p.completion_percentage for p in all_progress) / len(all_progress))
                last_activity = max(p.last_accessed for p in all_progress if p.last_accessed)

            students_data.append({
                "student_id": student.id,
                "student_name": student.name,
                "student_email": student.email,
                "student_avatar": student.avatar_url,
                "group_name": group_name,
                "course_id": course.id,
                "course_title": course.title,
                "current_lesson_id": current_lesson_id,
                "current_lesson_title": current_lesson_title or "Not started",
                "lesson_progress": lesson_progress_percentage,
                "overall_progress": overall_progress,
                "last_activity": last_activity
            })
        
        student_ids_seen.add(gs.student_id)
    
    # Sort by last activity (most recent first), then by student name
    students_data.sort(key=lambda x: (x["last_activity"] or datetime.min, x["student_name"]), reverse=True)
    
    return {"students_progress": students_data}


@router.get("/curator/students-progress")
async def get_curator_students_progress(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get list of students with their current lesson progress for curator's groups"""
    if current_user.role != "curator":
        raise HTTPException(status_code=403, detail="Only curators can access this endpoint")
    
    from src.schemas.models import CourseGroupAccess, Group
    
    # Get curator's groups
    curator_groups = db.query(Group).filter(
        Group.curator_id == current_user.id
    ).all()
    
    if not curator_groups:
        return {"students_progress": []}
    
    curator_group_ids = [g.id for g in curator_groups]
    curator_groups_map = {g.id: g for g in curator_groups}
    
    # Get all students from curator's groups with their group info
    group_student_records = db.query(GroupStudent).filter(
        GroupStudent.group_id.in_(curator_group_ids)
    ).all()
    
    if not group_student_records:
        return {"students_progress": []}
    
    students_data = []
    student_ids_seen = set()
    
    # Process each student from curator's groups
    for gs in group_student_records:
        if gs.student_id in student_ids_seen:
            continue
            
        student = db.query(UserInDB).filter(UserInDB.id == gs.student_id).first()
        if not student:
            continue
        
        group = curator_groups_map.get(gs.group_id)
        group_name = group.name if group else None
        
        # Get courses that this student's group has access to
        group_course_access = db.query(CourseGroupAccess).filter(
            CourseGroupAccess.group_id == gs.group_id,
            CourseGroupAccess.is_active == True
        ).all()
        
        if not group_course_access:
            # Student has no courses assigned - still show them
            students_data.append({
                "student_id": student.id,
                "student_name": student.name,
                "student_email": student.email,
                "student_avatar": student.avatar_url,
                "group_name": group_name,
                "course_id": None,
                "course_title": "No courses assigned",
                "current_lesson_id": None,
                "current_lesson_title": "Not started",
                "lesson_progress": 0,
                "overall_progress": 0,
                "last_activity": None
            })
            student_ids_seen.add(gs.student_id)
            continue
        
        # For each course the student has access to
        for access in group_course_access:
            course = db.query(Course).filter(
                Course.id == access.course_id,
                Course.is_active == True
            ).first()
            
            if not course:
                continue
            
            # Find last accessed lesson through StepProgress
            last_step_progress = db.query(StepProgress).filter(
                StepProgress.user_id == student.id,
                StepProgress.course_id == course.id
            ).order_by(desc(StepProgress.visited_at)).first()
            
            current_lesson_title = None
            current_lesson_id = None
            lesson_progress_percentage = 0
            
            if last_step_progress:
                # Get the lesson from the step
                step = db.query(Step).filter(Step.id == last_step_progress.step_id).first()
                if step:
                    lesson = db.query(Lesson).filter(Lesson.id == step.lesson_id).first()
                    if lesson:
                        current_lesson_title = lesson.title
                        current_lesson_id = lesson.id
                        
                        # Calculate lesson progress (completed steps / total steps in lesson)
                        lesson_steps = db.query(Step).filter(Step.lesson_id == lesson.id).count()
                        completed_lesson_steps = db.query(StepProgress).filter(
                            StepProgress.user_id == student.id,
                            StepProgress.step_id.in_(
                                db.query(Step.id).filter(Step.lesson_id == lesson.id)
                            ),
                            StepProgress.status == 'completed'
                        ).count()
                        
                        lesson_progress_percentage = round((completed_lesson_steps / lesson_steps) * 100) if lesson_steps > 0 else 0
            
            # Calculate overall course progress and get last activity
            all_progress = db.query(StudentProgress).filter(
                StudentProgress.user_id == student.id,
                StudentProgress.course_id == course.id
            ).all()
            
            overall_progress = 0
            last_activity = None
            
            if all_progress:
                overall_progress = round(sum(p.completion_percentage for p in all_progress) / len(all_progress))
                last_activity = max(p.last_accessed for p in all_progress if p.last_accessed)

            students_data.append({
                "student_id": student.id,
                "student_name": student.name,
                "student_email": student.email,
                "student_avatar": student.avatar_url,
                "group_name": group_name,
                "course_id": course.id,
                "course_title": course.title,
                "current_lesson_id": current_lesson_id,
                "current_lesson_title": current_lesson_title or "Not started",
                "lesson_progress": lesson_progress_percentage,
                "overall_progress": overall_progress,
                "last_activity": last_activity
            })
        
        student_ids_seen.add(gs.student_id)
    
    # Sort by last activity (most recent first), then by student name
    students_data.sort(key=lambda x: (x["last_activity"] or datetime.min, x["student_name"]), reverse=True)
    
    return {"students_progress": students_data}

@router.get("/curator/pending-submissions")
async def get_curator_pending_submissions(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get pending submissions for curator's students"""
    if current_user.role != "curator":
        raise HTTPException(status_code=403, detail="Only curators can access this endpoint")
    
    from src.schemas.models import Assignment, AssignmentSubmission, CourseGroupAccess, Group
    
    # Get curator's groups
    curator_groups = db.query(Group).filter(
        Group.curator_id == current_user.id
    ).all()
    
    if not curator_groups:
        return {"pending_submissions": []}
    
    curator_group_ids = [g.id for g in curator_groups]
    
    # Get students from curator's groups
    curator_student_ids = set()
    group_students = db.query(GroupStudent).filter(
        GroupStudent.group_id.in_(curator_group_ids)
    ).all()
    for gs in group_students:
        curator_student_ids.add(gs.student_id)
    
    if not curator_student_ids:
        return {"pending_submissions": []}
    
    # Get courses that curator's groups have access to
    course_ids = db.query(CourseGroupAccess.course_id).filter(
        CourseGroupAccess.group_id.in_(curator_group_ids),
        CourseGroupAccess.is_active == True
    ).distinct().all()
    course_ids = [c[0] for c in course_ids]
    
    if not course_ids:
        return {"pending_submissions": []}
    
    # Get assignments from those courses
    assignments = db.query(Assignment).filter(
        Assignment.lesson_id.in_(
            db.query(Lesson.id).filter(
                Lesson.module_id.in_(
                    db.query(Module.id).filter(
                        Module.course_id.in_(course_ids)
                    )
                )
            )
        ),
        Assignment.is_active == True
    ).all()
    
    if not assignments:
        return {"pending_submissions": []}
    
    # Get pending submissions ONLY from curator's students
    pending_submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id.in_([a.id for a in assignments]),
        AssignmentSubmission.user_id.in_(curator_student_ids),
        AssignmentSubmission.is_graded == False
    ).all()
    
    submissions_data = []
    for submission in pending_submissions:
        # Get assignment details
        assignment = db.query(Assignment).filter(Assignment.id == submission.assignment_id).first()
        
        # Get student details
        student = db.query(UserInDB).filter(UserInDB.id == submission.user_id).first()
        
        # Get course details
        course = None
        if assignment and assignment.lesson_id:
            lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
            if lesson:
                module = db.query(Module).filter(Module.id == lesson.module_id).first()
                if module:
                    course = db.query(Course).filter(Course.id == module.course_id).first()
        
        submissions_data.append({
            "id": submission.id,
            "assignment_id": submission.assignment_id,
            "assignment_title": assignment.title if assignment else "Unknown Assignment",
            "course_title": course.title if course else "Unknown Course",
            "user_id": submission.user_id,
            "student_name": student.name if student else "Unknown Student",
            "student_email": student.email if student else "",
            "submitted_at": submission.submitted_at,
            "max_score": submission.max_score,
            "file_url": submission.file_url,
            "submitted_file_name": submission.submitted_file_name
        })
    
    # Sort by submission date (most recent first), handling potential None values
    submissions_data.sort(key=lambda x: x["submitted_at"] if x["submitted_at"] is not None else datetime.min, reverse=True)
    
    return {"pending_submissions": submissions_data}

@router.get("/curator/recent-submissions")
async def get_curator_recent_submissions(
    limit: int = 10,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get recent submissions for curator's students"""
    if current_user.role != "curator":
        raise HTTPException(status_code=403, detail="Only curators can access this endpoint")
    
    from src.schemas.models import Assignment, AssignmentSubmission, CourseGroupAccess, Group
    
    # Get curator's groups
    curator_groups = db.query(Group).filter(
        Group.curator_id == current_user.id
    ).all()
    
    if not curator_groups:
        return {"recent_submissions": []}
    
    curator_group_ids = [g.id for g in curator_groups]
    
    # Get students from curator's groups
    curator_student_ids = set()
    group_students = db.query(GroupStudent).filter(
        GroupStudent.group_id.in_(curator_group_ids)
    ).all()
    for gs in group_students:
        curator_student_ids.add(gs.student_id)
    
    if not curator_student_ids:
        return {"recent_submissions": []}
    
    # Get courses that curator's groups have access to
    course_ids = db.query(CourseGroupAccess.course_id).filter(
        CourseGroupAccess.group_id.in_(curator_group_ids),
        CourseGroupAccess.is_active == True
    ).distinct().all()
    course_ids = [c[0] for c in course_ids]
    
    if not course_ids:
        return {"recent_submissions": []}
    
    # Get assignments
    assignments = db.query(Assignment).filter(
        Assignment.lesson_id.in_(
            db.query(Lesson.id).filter(
                Lesson.module_id.in_(
                    db.query(Module.id).filter(
                        Module.course_id.in_(course_ids)
                    )
                )
            )
        ),
        Assignment.is_active == True
    ).all()
    
    if not assignments:
        return {"recent_submissions": []}
    
    # Get recent submissions
    recent_submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id.in_([a.id for a in assignments]),
        AssignmentSubmission.user_id.in_(curator_student_ids)
    ).order_by(desc(AssignmentSubmission.submitted_at)).limit(limit).all()
    
    submissions_data = []
    for submission in recent_submissions:
        # Get assignment details
        assignment = db.query(Assignment).filter(Assignment.id == submission.assignment_id).first()
        
        # Get student details
        student = db.query(UserInDB).filter(UserInDB.id == submission.user_id).first()
        
        # Get course details
        course = None
        if assignment and assignment.lesson_id:
            lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
            if lesson:
                module = db.query(Module).filter(Module.id == lesson.module_id).first()
                if module:
                    course = db.query(Course).filter(Course.id == module.course_id).first()
                    
        # Get grader details
        grader_name = None
        if submission.graded_by:
            grader = db.query(UserInDB).filter(UserInDB.id == submission.graded_by).first()
            grader_name = grader.name if grader else None
        
        submissions_data.append({
            "id": submission.id,
            "assignment_id": submission.assignment_id,
            "assignment_title": assignment.title if assignment else "Unknown Assignment",
            "course_title": course.title if course else "Unknown Course",
            "user_id": submission.user_id,
            "student_name": student.name if student else "Unknown Student",
            "student_email": student.email if student else "",
            "submitted_at": submission.submitted_at,
            "graded_at": submission.graded_at,
            "score": submission.score,
            "max_score": submission.max_score,
            "is_graded": submission.is_graded,
            "feedback": submission.feedback,
            "grader_name": grader_name,
            "file_url": submission.file_url,
            "submitted_file_name": submission.submitted_file_name
        })
    
    return {"recent_submissions": submissions_data}
@router.get("/curator/assignments-analytics")
async def get_curator_assignments_analytics(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get analytics for assignments relevant to curator's groups"""
    if current_user.role != "curator":
        raise HTTPException(status_code=403, detail="Only curators can access this endpoint")
    
    from src.schemas.models import Assignment, AssignmentSubmission, CourseGroupAccess, Group
    
    # Get curator's groups
    curator_groups = db.query(Group).filter(
        Group.curator_id == current_user.id
    ).all()
    
    if not curator_groups:
        return {"assignments": []}
    
    curator_group_ids = [g.id for g in curator_groups]
    
    # Get students from curator's groups
    curator_student_ids = set()
    group_students = db.query(GroupStudent).filter(
        GroupStudent.group_id.in_(curator_group_ids)
    ).all()
    for gs in group_students:
        curator_student_ids.add(gs.student_id)
    
    if not curator_student_ids:
        return {"assignments": []}
    
    # Get courses that curator's groups have access to
    course_ids = db.query(CourseGroupAccess.course_id).filter(
        CourseGroupAccess.group_id.in_(curator_group_ids),
        CourseGroupAccess.is_active == True
    ).distinct().all()
    course_ids = [c[0] for c in course_ids]
    
    # Get assignments - BOTH lesson-based AND group-based
    # Lesson-based assignments from courses
    lesson_based_assignments = db.query(Assignment).filter(
        Assignment.lesson_id.in_(
            db.query(Lesson.id).filter(
                Lesson.module_id.in_(
                    db.query(Module.id).filter(
                        Module.course_id.in_(course_ids)
                    )
                )
            )
        ),
        Assignment.is_active == True,
        Assignment.is_hidden == False
    ).all()
    
    # Group-based assignments (no lesson_id, but have group_id)
    group_based_assignments = db.query(Assignment).filter(
        Assignment.group_id.in_(curator_group_ids),
        Assignment.lesson_id.is_(None),  # Only assignments without lesson_id
        Assignment.is_active == True,
        Assignment.is_hidden == False
    ).all()
    
    # Combine both types
    assignments = lesson_based_assignments + group_based_assignments
    
    if not assignments:
        return {"assignments": []}
    
    # Get all submissions for these assignments filtered by curator students
    all_submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id.in_([a.id for a in assignments]),
        AssignmentSubmission.user_id.in_(curator_student_ids),
        AssignmentSubmission.is_hidden == False
    ).all()
    
    # Group submissions by assignment
    submissions_by_assignment = {}
    for sub in all_submissions:
        if sub.assignment_id not in submissions_by_assignment:
            submissions_by_assignment[sub.assignment_id] = []
        submissions_by_assignment[sub.assignment_id].append(sub)
            
    # Prepare result
    results = []
    for assignment in assignments:
        subs = submissions_by_assignment.get(assignment.id, [])
        submitted_count = len(subs)
        graded_count = len([s for s in subs if s.is_graded])
        
        scores = [s.score for s in subs if s.is_graded and s.score is not None]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        # Get course info and count enrolled students from curator's groups
        course_title = "Unknown Course"
        total_students_for_assignment = 0
        
        if assignment.lesson_id:
            # Lesson-based assignment - get course from lesson hierarchy
            lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
            if lesson:
                module = db.query(Module).filter(Module.id == lesson.module_id).first()
                if module:
                    course = db.query(Course).filter(Course.id == module.course_id).first()
                    if course:
                        course_title = course.title
                        
                        # Count students from curator's groups enrolled in this course
                        enrolled_curator_students = db.query(Enrollment).filter(
                            Enrollment.course_id == course.id,
                            Enrollment.user_id.in_(curator_student_ids),
                            Enrollment.is_active == True
                        ).count()
                        total_students_for_assignment = enrolled_curator_students
        elif assignment.group_id:
            # Group-based assignment - get group name as "course"
            group = db.query(Group).filter(Group.id == assignment.group_id).first()
            if group:
                course_title = f"Group: {group.name}"
                
                # Count students in this specific group
                students_in_group = db.query(GroupStudent).filter(
                    GroupStudent.group_id == assignment.group_id
                ).count()
                total_students_for_assignment = students_in_group

        results.append({
            "id": assignment.id,
            "title": assignment.title,
            "course_title": course_title,
            "due_date": assignment.due_date,
            "max_score": assignment.max_score,
            "total_students": total_students_for_assignment,
            "submitted_count": submitted_count,
            "graded_count": graded_count,
            "average_score": round(avg_score, 1)
        })
        
    # Sort by due date (descending) or title
    results.sort(key=lambda x: x["due_date"] or datetime.min, reverse=True)
    
    return {"assignments": results}


@router.get("/curator/homework-by-group")
async def get_curator_homework_by_group(
    group_id: Optional[int] = None,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get homework data grouped by curator's groups with detailed student submissions.
    Returns groups with their assignments and student progress.
    """
    if current_user.role != "curator":
        raise HTTPException(status_code=403, detail="Only curators can access this endpoint")
    
    from src.schemas.models import Assignment, AssignmentSubmission, CourseGroupAccess, Group
    
    # Get curator's groups
    curator_groups_query = db.query(Group).filter(Group.curator_id == current_user.id)
    if group_id:
        curator_groups_query = curator_groups_query.filter(Group.id == group_id)
    
    curator_groups = curator_groups_query.all()
    
    if not curator_groups:
        return {"groups": []}
    
    result = []
    
    for group in curator_groups:
        # Get students in this group
        group_student_ids = [gs.student_id for gs in db.query(GroupStudent).filter(
            GroupStudent.group_id == group.id
        ).all()]
        
        if not group_student_ids:
            result.append({
                "group_id": group.id,
                "group_name": group.name,
                "students_count": 0,
                "assignments": []
            })
            continue
        
        # Get students info
        students = db.query(UserInDB).filter(UserInDB.id.in_(group_student_ids)).all()
        students_map = {s.id: s for s in students}
        
        # Get courses that this group has access to
        course_access = db.query(CourseGroupAccess).filter(
            CourseGroupAccess.group_id == group.id,
            CourseGroupAccess.is_active == True
        ).all()
        course_ids = [ca.course_id for ca in course_access]
        
        # Get lesson-based assignments from those courses
        lesson_based_assignments = []
        if course_ids:
            lesson_ids = db.query(Lesson.id).filter(
                Lesson.module_id.in_(
                    db.query(Module.id).filter(Module.course_id.in_(course_ids))
                )
            ).all()
            lesson_ids = [l[0] for l in lesson_ids]
            
            if lesson_ids:
                lesson_based_assignments = db.query(Assignment).filter(
                    Assignment.lesson_id.in_(lesson_ids),
                    Assignment.is_active == True,
                    (Assignment.is_hidden == False) | (Assignment.is_hidden.is_(None))
                ).all()
        
        # Get group-based assignments
        group_based_assignments = db.query(Assignment).filter(
            Assignment.group_id == group.id,
            Assignment.lesson_id.is_(None),
            Assignment.is_active == True,
            (Assignment.is_hidden == False) | (Assignment.is_hidden.is_(None))
        ).all()
        
        # Combine assignments
        all_assignments = lesson_based_assignments + group_based_assignments
        
        assignments_data = []
        for assignment in all_assignments:
            # Get course info
            course_title = "Unknown"
            if assignment.lesson_id:
                lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
                if lesson:
                    module = db.query(Module).filter(Module.id == lesson.module_id).first()
                    if module:
                        course = db.query(Course).filter(Course.id == module.course_id).first()
                        if course:
                            course_title = course.title
            elif assignment.group_id:
                course_title = f"Group Assignment"
            
            # Get submissions for this assignment from group students
            submissions = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.assignment_id == assignment.id,
                AssignmentSubmission.user_id.in_(group_student_ids),
                AssignmentSubmission.is_hidden == False
            ).all()
            
            submissions_map = {s.user_id: s for s in submissions}
            
            # Build student progress list
            students_progress = []
            for student_id in group_student_ids:
                student = students_map.get(student_id)
                if not student:
                    continue
                
                submission = submissions_map.get(student_id)
                
                # Determine status
                status = 'not_submitted'
                if submission:
                    if submission.is_graded:
                        status = 'graded'
                    else:
                        status = 'submitted'
                elif assignment.due_date and assignment.due_date < datetime.utcnow():
                    status = 'overdue'
                
                students_progress.append({
                    "student_id": student.id,
                    "student_name": student.name,
                    "student_email": student.email,
                    "status": status,
                    "submission_id": submission.id if submission else None,
                    "score": submission.score if submission else None,
                    "max_score": assignment.max_score,
                    "submitted_at": submission.submitted_at.isoformat() if submission and submission.submitted_at else None,
                    "graded_at": submission.graded_at.isoformat() if submission and submission.graded_at else None,
                    "feedback": submission.feedback if submission else None
                })
            
            # Calculate summary
            submitted_count = len([s for s in students_progress if s["status"] in ['submitted', 'graded']])
            graded_count = len([s for s in students_progress if s["status"] == 'graded'])
            not_submitted_count = len([s for s in students_progress if s["status"] == 'not_submitted'])
            overdue_count = len([s for s in students_progress if s["status"] == 'overdue'])
            
            scores = [s["score"] for s in students_progress if s["score"] is not None]
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0
            
            # Parse assignment content
            assignment_content = None
            if assignment.content:
                try:
                    assignment_content = json.loads(assignment.content) if isinstance(assignment.content, str) else assignment.content
                except:
                    assignment_content = None
            
            assignments_data.append({
                "id": assignment.id,
                "title": assignment.title,
                "description": assignment.description,
                "course_title": course_title,
                "due_date": assignment.due_date.isoformat() if assignment.due_date else None,
                "max_score": assignment.max_score,
                "assignment_type": assignment.assignment_type,
                "content": assignment_content,
                "summary": {
                    "total_students": len(group_student_ids),
                    "submitted": submitted_count,
                    "graded": graded_count,
                    "not_submitted": not_submitted_count,
                    "overdue": overdue_count,
                    "average_score": avg_score
                },
                "students": students_progress
            })
        
        # Sort assignments by due date (most recent first)
        assignments_data.sort(key=lambda x: x["due_date"] or "9999-99-99", reverse=True)
        
        result.append({
            "group_id": group.id,
            "group_name": group.name,
            "students_count": len(group_student_ids),
            "assignments": assignments_data
        })
    
    return {"groups": result}
