from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from typing import List, Optional
from datetime import datetime, timedelta

from src.config import get_db
from src.schemas.models import (
    UserInDB, Course, Module, Lesson, Enrollment, StudentProgress,
    DashboardStatsSchema, CourseProgressSchema, UserSchema
)
from src.routes.auth import get_current_user_dependency
from src.utils.permissions import require_role
from src.schemas.models import GroupStudent

router = APIRouter()

@router.get("/stats", response_model=DashboardStatsSchema)
def get_dashboard_stats(
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
    total_study_time_hours = user.total_study_time_minutes // 60
    
    # Calculate average progress across all courses
    total_progress = 0
    course_progresses = []
    
    for course in all_courses:
        # Get course progress
        course_progress_records = db.query(StudentProgress).filter(
            StudentProgress.user_id == user.id,
            StudentProgress.course_id == course.id
        ).all()
        
        if course_progress_records:
            # Calculate average progress for this course
            course_avg_progress = sum(p.completion_percentage for p in course_progress_records) / len(course_progress_records)
        else:
            course_avg_progress = 0
        
        total_progress += course_avg_progress
        
        # Get teacher info
        teacher = db.query(UserInDB).filter(UserInDB.id == course.teacher_id).first()
        teacher_name = teacher.name if teacher else "Unknown Teacher"
        
        # Count total modules in course
        total_modules = db.query(Module).filter(Module.course_id == course.id).count()
        
        # Get last accessed time
        last_progress = db.query(StudentProgress).filter(
            StudentProgress.user_id == user.id,
            StudentProgress.course_id == course.id
        ).order_by(desc(StudentProgress.last_accessed)).first()
        
        course_progresses.append({
            "id": course.id,
            "title": course.title,
            "cover_image": course.cover_image_url,
            "teacher": teacher_name,
            "total_modules": total_modules,
            "progress": round(course_avg_progress),
            "status": "completed" if course_avg_progress >= 100 else "in_progress" if course_avg_progress > 0 else "not_started",
            "last_accessed": last_progress.last_accessed if last_progress else datetime.utcnow()
        })
    
    # Calculate overall average progress
    average_progress = round(total_progress / enrolled_courses_count) if enrolled_courses_count > 0 else 0
    
    # Sort courses by last accessed (most recent first)
    course_progresses.sort(key=lambda x: x["last_accessed"], reverse=True)
    
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
    # Get teacher's courses
    teacher_courses = db.query(Course).filter(
        Course.teacher_id == user.id,
        Course.is_active == True
    ).all()
    
    total_courses = len(teacher_courses)
    total_students = 0
    total_assignments = 0
    pending_submissions = 0
    recent_enrollments = 0
    total_completion_rate = 0
    upcoming_deadlines = 0
    avg_student_score = 0
    total_submissions = 0
    graded_submissions = 0
    
    # Get teacher's assignments
    from src.schemas.models import Assignment
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
    total_assignments = len(teacher_assignments)
    
    # Get pending submissions (ungraded)
    from src.schemas.models import AssignmentSubmission
    pending_submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id.in_([a.id for a in teacher_assignments]),
        AssignmentSubmission.is_graded == False
    ).count()
    
    # Get total submissions and graded submissions for score calculation
    total_submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id.in_([a.id for a in teacher_assignments])
    ).count()
    
    graded_submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id.in_([a.id for a in teacher_assignments]),
        AssignmentSubmission.is_graded == True,
        AssignmentSubmission.score.isnot(None)
    ).all()
    
    # Calculate average student score
    if graded_submissions:
        total_score = sum(sub.score for sub in graded_submissions)
        avg_student_score = round(total_score / len(graded_submissions))
    
    # Get recent enrollments (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_enrollments = db.query(Enrollment).filter(
        Enrollment.course_id.in_([c.id for c in teacher_courses]),
        Enrollment.enrolled_at >= seven_days_ago,
        Enrollment.is_active == True
    ).count()
    
    # Get upcoming deadlines (next 7 days)
    seven_days_from_now = datetime.utcnow() + timedelta(days=7)
    upcoming_deadlines = db.query(Assignment).filter(
        Assignment.lesson_id.in_(
            db.query(Lesson.id).filter(
                Lesson.module_id.in_(
                    db.query(Module.id).filter(
                        Module.course_id.in_([c.id for c in teacher_courses])
                    )
                )
            )
        ),
        Assignment.is_active == True,
        Assignment.due_date.isnot(None),
        Assignment.due_date >= datetime.utcnow(),
        Assignment.due_date <= seven_days_from_now
    ).count()
    
    course_stats = []
    
    for course in teacher_courses:
        # Count enrolled students
        enrolled_students = db.query(Enrollment).filter(
            Enrollment.course_id == course.id,
            Enrollment.is_active == True
        ).count()
        total_students += enrolled_students
        
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
        
        # Get course assignments
        course_assignments = db.query(Assignment).filter(
            Assignment.lesson_id.in_(
                db.query(Lesson.id).filter(
                    Lesson.module_id.in_(
                        db.query(Module.id).filter(Module.course_id == course.id)
                    )
                )
            ),
            Assignment.is_active == True
        ).count()
        
        # Get course completion rate
        course_completion_rate = 0
        if enrolled_students > 0:
            completed_enrollments = db.query(Enrollment).filter(
                Enrollment.course_id == course.id,
                Enrollment.is_active == True,
                Enrollment.completed_at.isnot(None)
            ).count()
            course_completion_rate = round((completed_enrollments / enrolled_students) * 100)
        
        course_stats.append({
            "id": course.id,
            "title": course.title,
            "cover_image": course.cover_image_url,
            "teacher": user.name,
            "total_modules": total_modules,
            "enrolled_students": enrolled_students,
            "total_assignments": course_assignments,
            "completion_rate": course_completion_rate,
            "progress": round(avg_progress),
            "status": "active",
            "last_accessed": course.updated_at
        })
    
    # Calculate average completion rate
    avg_completion_rate = round(total_completion_rate / total_courses) if total_courses > 0 else 0
    
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
            "total_assignments": total_assignments,
            "pending_submissions": pending_submissions,
            "recent_enrollments": recent_enrollments,
            "avg_completion_rate": avg_completion_rate,
            "upcoming_deadlines": upcoming_deadlines,
            "avg_student_score": avg_student_score,
            "total_submissions": total_submissions,
            "graded_submissions": len(graded_submissions),
            "grading_progress": round((len(graded_submissions) / total_submissions) * 100) if total_submissions > 0 else 0
        },
        recent_courses=course_stats[:6]
    )

def get_curator_dashboard_stats(user: UserInDB, db: Session) -> DashboardStatsSchema:
    """Get dashboard stats for curator"""
    # Get students assigned to curator (same group)
    assigned_students = []
    if user.group_id:
        # Get students in curator's group using GroupStudent association table
        group_student_ids = db.query(GroupStudent.student_id).filter(
            GroupStudent.group_id == user.group_id
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
def get_my_courses(
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
def get_recent_activity(
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
def update_study_time(
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
def get_teacher_pending_submissions(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get pending submissions for teacher's assignments"""
    if current_user.role not in ["teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only teachers can access this endpoint")
    
    # Get teacher's courses
    teacher_courses = db.query(Course).filter(
        Course.teacher_id == current_user.id,
        Course.is_active == True
    ).all()
    
    if not teacher_courses:
        return {"pending_submissions": []}
    
    # Get teacher's assignments
    from src.schemas.models import Assignment, AssignmentSubmission
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
    
    if not teacher_assignments:
        return {"pending_submissions": []}
    
    # Get pending submissions with details
    pending_submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id.in_([a.id for a in teacher_assignments]),
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
            "student_id": submission.user_id,
            "student_name": student.name if student else "Unknown Student",
            "student_email": student.email if student else "",
            "submitted_at": submission.submitted_at,
            "max_score": submission.max_score,
            "file_url": submission.file_url,
            "submitted_file_name": submission.submitted_file_name
        })
    
    # Sort by submission date (most recent first)
    submissions_data.sort(key=lambda x: x["submitted_at"], reverse=True)
    
    return {"pending_submissions": submissions_data}

@router.get("/teacher/recent-submissions")
def get_teacher_recent_submissions(
    limit: int = 10,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get recent submissions for teacher's assignments (both graded and ungraded)"""
    if current_user.role not in ["teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only teachers can access this endpoint")
    
    # Get teacher's courses
    teacher_courses = db.query(Course).filter(
        Course.teacher_id == current_user.id,
        Course.is_active == True
    ).all()
    
    if not teacher_courses:
        return {"recent_submissions": []}
    
    # Get teacher's assignments
    from src.schemas.models import Assignment, AssignmentSubmission
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
    
    if not teacher_assignments:
        return {"recent_submissions": []}
    
    # Get recent submissions with details
    recent_submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id.in_([a.id for a in teacher_assignments])
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
            "student_id": submission.user_id,
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
