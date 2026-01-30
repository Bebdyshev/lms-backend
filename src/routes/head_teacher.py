from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, timedelta, date
from pydantic import BaseModel

from src.config import get_db
from src.schemas.models import (
    UserInDB, Course, Group, GroupStudent, CourseGroupAccess,
    AssignmentSubmission, Assignment, QuizAttempt, CourseHeadTeacher
)
from src.routes.auth import get_current_user_dependency

router = APIRouter()


# ==============================================================================
# Pydantic Schemas
# ==============================================================================

class HeadTeacherCourseSchema(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    teacher_id: Optional[int] = None
    teacher_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TeacherStatisticsSchema(BaseModel):
    teacher_id: int
    teacher_name: str
    email: str
    last_activity_date: Optional[date] = None
    groups_count: int
    students_count: int
    # Homework Stats
    checked_homeworks_count: int
    feedbacks_given_count: int
    avg_grading_time_hours: Optional[float] = None  # Avg time between submission and grading
    # Quiz Stats
    quizzes_graded_count: int
    # Recent Activity
    homeworks_checked_last_7_days: int
    homeworks_checked_last_30_days: int


class CourseTeacherStatsResponse(BaseModel):
    course_id: int
    course_title: str
    date_range_start: Optional[date] = None
    date_range_end: Optional[date] = None
    teachers: List[TeacherStatisticsSchema]


class GradeDistributionItem(BaseModel):
    score_range: str  # e.g., "0-20", "21-40", "41-60", "61-80", "81-100"
    count: int


class ActivityHistoryItem(BaseModel):
    date: date
    submissions_graded: int


class TeacherDetailsResponse(BaseModel):
    teacher_id: int
    teacher_name: str
    email: str
    avatar_url: Optional[str] = None
    groups_count: int
    students_count: int
    grade_distribution: List[GradeDistributionItem]
    activity_history: List[ActivityHistoryItem]  # Last 30 days
    total_feedbacks: int
    avg_score_given: Optional[float] = None


class FeedbackItem(BaseModel):
    submission_id: int
    student_name: str
    assignment_title: str
    score: Optional[float] = None
    max_score: float
    feedback: str
    graded_at: datetime


class TeacherFeedbacksResponse(BaseModel):
    teacher_id: int
    teacher_name: str
    feedbacks: List[FeedbackItem]
    total: int


class AssignmentItem(BaseModel):
    assignment_id: int
    title: str
    group_name: str
    due_date: Optional[datetime] = None
    total_submissions: int
    graded_submissions: int
    created_at: datetime


class TeacherAssignmentsResponse(BaseModel):
    teacher_id: int
    teacher_name: str
    assignments: List[AssignmentItem]
    total: int


# ==============================================================================
# Endpoints
# ==============================================================================

@router.get("/courses", response_model=List[HeadTeacherCourseSchema])
async def get_managed_courses(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get list of courses managed by the current Head Teacher.
    """
    if current_user.role not in ["head_teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only Head Teachers and Admins can access this endpoint")
    
    if current_user.role == "admin":
        # Admins see all courses
        courses = db.query(Course).filter(Course.is_active == True).all()
    else:
        # Head Teachers see only their managed courses via M2M table
        courses = db.query(Course).join(
            CourseHeadTeacher, CourseHeadTeacher.course_id == Course.id
        ).filter(
            CourseHeadTeacher.head_teacher_id == current_user.id
        ).all()
    
    result = []
    for course in courses:
        teacher_name = course.teacher.name if course.teacher else None
        result.append(HeadTeacherCourseSchema(
            id=course.id,
            title=course.title,
            description=course.description,
            teacher_id=course.teacher_id,
            teacher_name=teacher_name,
            is_active=course.is_active,
            created_at=course.created_at
        ))
    return result


@router.get("/course/{course_id}/teachers", response_model=CourseTeacherStatsResponse)
async def get_course_teacher_statistics(
    course_id: int,
    days: int = Query(30, ge=0, le=365, description="Number of past days for statistics"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get detailed statistics for all teachers working with groups linked to a specific course.
    Supports custom date range filtering.
    """
    # Authorization
    if current_user.role not in ["head_teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only Head Teachers and Admins can access this endpoint")
    
    # If Head Teacher, verify they manage this course
    if current_user.role == "head_teacher":
        access = db.query(CourseHeadTeacher).filter(
            CourseHeadTeacher.course_id == course_id,
            CourseHeadTeacher.head_teacher_id == current_user.id
        ).first()
        if not access:
            raise HTTPException(status_code=403, detail="You do not manage this course")
    
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Get groups linked to this course
    group_accesses = db.query(CourseGroupAccess).filter(
        CourseGroupAccess.course_id == course_id,
        CourseGroupAccess.is_active == True
    ).all()
    group_ids = [ga.group_id for ga in group_accesses]
    
    if not group_ids:
        return CourseTeacherStatsResponse(
            course_id=course_id,
            course_title=course.title,
            teachers=[],
            daily_activity=[]
        )
    
    # Date ranges logic
    now = datetime.utcnow()
    
    if start_date and end_date:
        date_range_start = start_date
        date_range_end = end_date
    else:
        date_range_end = now.date()
        date_range_start = (now - timedelta(days=days)).date()
        
    date_7_days_ago = now - timedelta(days=7)
    date_30_days_ago = now - timedelta(days=30)
    
    # Daily Activity Query for the whole course
    # Get all assignments linked to these groups
    all_course_assignment_ids = db.query(Assignment.id).filter(
        Assignment.group_id.in_(group_ids),
        Assignment.is_active == True
    ).subquery()
    
    course_activity_data = db.query(
        func.date(AssignmentSubmission.graded_at).label('graded_date'),
        func.count(AssignmentSubmission.id).label('count')
    ).filter(
        AssignmentSubmission.assignment_id.in_(all_course_assignment_ids),
        AssignmentSubmission.is_graded == True,
        AssignmentSubmission.graded_at >= date_range_start,
        AssignmentSubmission.graded_at <= datetime.combine(date_range_end, datetime.max.time())
    ).group_by(
        func.date(AssignmentSubmission.graded_at)
    ).order_by(
        func.date(AssignmentSubmission.graded_at)
    ).all()
    
    daily_activity = [
        ActivityHistoryItem(date=item.graded_date, submissions_graded=item.count)
        for item in course_activity_data
    ]

    # Get groups and their teachers
    groups = db.query(Group).filter(Group.id.in_(group_ids)).all()
    
    # Build teacher -> groups mapping
    teacher_groups = {}  # teacher_id -> list of group_ids
    for group in groups:
        if group.teacher_id:
            if group.teacher_id not in teacher_groups:
                teacher_groups[group.teacher_id] = []
            teacher_groups[group.teacher_id].append(group.id)
    
    teacher_ids = list(teacher_groups.keys())
    if not teacher_ids:
        return CourseTeacherStatsResponse(
            course_id=course_id,
            course_title=course.title,
            teachers=[],
            daily_activity=daily_activity
        )
    
    # Fetch teacher users
    teachers = db.query(UserInDB).filter(UserInDB.id.in_(teacher_ids)).all()
    teachers_map = {t.id: t for t in teachers}
    
    # Build response
    teacher_stats = []
    
    for teacher_id, group_ids_for_teacher in teacher_groups.items():
        teacher = teachers_map.get(teacher_id)
        if not teacher:
            continue
        
        # Students count in groups
        students_count = db.query(func.count(GroupStudent.id)).filter(
            GroupStudent.group_id.in_(group_ids_for_teacher)
        ).scalar() or 0
        
        # Get assignments for these groups
        assignment_ids_query = db.query(Assignment.id).filter(
            Assignment.group_id.in_(group_ids_for_teacher),
            Assignment.is_active == True
        ).subquery()
        
        # Homework grading stats (graded_by = this teacher)
        # Apply date filter!
        checked_homeworks_count = db.query(func.count(AssignmentSubmission.id)).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids_query),
            AssignmentSubmission.graded_by == teacher_id,
            AssignmentSubmission.is_graded == True,
            AssignmentSubmission.graded_at >= date_range_start,
            AssignmentSubmission.graded_at <= datetime.combine(date_range_end, datetime.max.time())
        ).scalar() or 0
        
        feedbacks_given_count = db.query(func.count(AssignmentSubmission.id)).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids_query),
            AssignmentSubmission.graded_by == teacher_id,
            AssignmentSubmission.is_graded == True,
            AssignmentSubmission.feedback.isnot(None),
            AssignmentSubmission.feedback != "",
            AssignmentSubmission.graded_at >= date_range_start,
            AssignmentSubmission.graded_at <= datetime.combine(date_range_end, datetime.max.time())
        ).scalar() or 0
        
        # Average grading time
        grading_times = db.query(
            func.avg(
                func.extract('epoch', AssignmentSubmission.graded_at) - 
                func.extract('epoch', AssignmentSubmission.submitted_at)
            )
        ).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids_query),
            AssignmentSubmission.graded_by == teacher_id,
            AssignmentSubmission.is_graded == True,
            AssignmentSubmission.graded_at.isnot(None),
            AssignmentSubmission.submitted_at.isnot(None),
            AssignmentSubmission.graded_at >= date_range_start,
            AssignmentSubmission.graded_at <= datetime.combine(date_range_end, datetime.max.time())
        ).scalar()
        
        avg_grading_time_hours = None
        if grading_times:
            avg_grading_time_hours = round(grading_times / 3600, 2)  # Convert seconds to hours
        
        # Recent activity (Still specifically last 7 and 30 days relative to NOW, not selected range, as these are "recent" indicators)
        # Or should they follow the range? The labels are "Last 7 Days". Let's keep them as fixed recent indicators.
        homeworks_checked_last_7_days = db.query(func.count(AssignmentSubmission.id)).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids_query),
            AssignmentSubmission.graded_by == teacher_id,
            AssignmentSubmission.is_graded == True,
            AssignmentSubmission.graded_at >= date_7_days_ago
        ).scalar() or 0
        
        homeworks_checked_last_30_days = db.query(func.count(AssignmentSubmission.id)).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids_query),
            AssignmentSubmission.graded_by == teacher_id,
            AssignmentSubmission.is_graded == True,
            AssignmentSubmission.graded_at >= date_30_days_ago
        ).scalar() or 0
        
        # Quiz grading (manual grading: is_graded=True, graded_by is set)
        quizzes_graded_count = db.query(func.count(QuizAttempt.id)).filter(
            QuizAttempt.course_id == course_id,
            QuizAttempt.graded_by == teacher_id,
            QuizAttempt.is_graded == True,
            QuizAttempt.is_draft == False
        ).scalar() or 0
        
        teacher_stats.append(TeacherStatisticsSchema(
            teacher_id=teacher_id,
            teacher_name=teacher.name,
            email=teacher.email,
            last_activity_date=teacher.last_activity_date,
            groups_count=len(group_ids_for_teacher),
            students_count=students_count,
            checked_homeworks_count=checked_homeworks_count,
            feedbacks_given_count=feedbacks_given_count,
            avg_grading_time_hours=avg_grading_time_hours,
            quizzes_graded_count=quizzes_graded_count,
            homeworks_checked_last_7_days=homeworks_checked_last_7_days,
            homeworks_checked_last_30_days=homeworks_checked_last_30_days
        ))
    
    # Sort by teacher name
    teacher_stats.sort(key=lambda x: x.teacher_name)
    
    return CourseTeacherStatsResponse(
        course_id=course_id,
        course_title=course.title,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        teachers=teacher_stats,
        daily_activity=daily_activity
    )


@router.get("/course/{course_id}/teacher/{teacher_id}/details", response_model=TeacherDetailsResponse)
async def get_teacher_details(
    course_id: int,
    teacher_id: int,
    days: int = Query(30, ge=1, le=365, description="Number of past days for activity history"),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get detailed analytics for a specific teacher in a course.
    Includes grade distribution, activity history, and summary stats.
    """
    # Authorization
    if current_user.role not in ["head_teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only Head Teachers and Admins can access this endpoint")
    
    if current_user.role == "head_teacher":
        access = db.query(CourseHeadTeacher).filter(
            CourseHeadTeacher.course_id == course_id,
            CourseHeadTeacher.head_teacher_id == current_user.id
        ).first()
        if not access:
            raise HTTPException(status_code=403, detail="You do not manage this course")
    
    # Verify teacher exists
    teacher = db.query(UserInDB).filter(UserInDB.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    # Get groups for this teacher in this course
    group_accesses = db.query(CourseGroupAccess).filter(
        CourseGroupAccess.course_id == course_id,
        CourseGroupAccess.is_active == True
    ).all()
    group_ids = [ga.group_id for ga in group_accesses]
    
    teacher_groups = db.query(Group).filter(
        Group.id.in_(group_ids),
        Group.teacher_id == teacher_id
    ).all()
    teacher_group_ids = [g.id for g in teacher_groups]
    
    # Students count
    students_count = db.query(func.count(GroupStudent.id)).filter(
        GroupStudent.group_id.in_(teacher_group_ids)
    ).scalar() or 0
    
    # Get assignments for these groups
    assignment_ids_query = db.query(Assignment.id).filter(
        Assignment.group_id.in_(teacher_group_ids),
        Assignment.is_active == True
    ).subquery()
    
    # Grade distribution (percentage-based)
    graded_submissions = db.query(
        AssignmentSubmission.score,
        AssignmentSubmission.max_score
    ).filter(
        AssignmentSubmission.assignment_id.in_(assignment_ids_query),
        AssignmentSubmission.graded_by == teacher_id,
        AssignmentSubmission.is_graded == True,
        AssignmentSubmission.score.isnot(None),
        AssignmentSubmission.max_score > 0
    ).all()
    
    # Calculate percentage and distribute into buckets
    grade_buckets = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    total_score = 0.0
    count = 0
    
    for score, max_score in graded_submissions:
        percentage = (score / max_score) * 100
        total_score += score
        count += 1
        
        if percentage <= 20:
            grade_buckets["0-20"] += 1
        elif percentage <= 40:
            grade_buckets["21-40"] += 1
        elif percentage <= 60:
            grade_buckets["41-60"] += 1
        elif percentage <= 80:
            grade_buckets["61-80"] += 1
        else:
            grade_buckets["81-100"] += 1
    
    grade_distribution = [
        GradeDistributionItem(score_range=k, count=v) 
        for k, v in grade_buckets.items()
    ]
    
    avg_score_given = round(total_score / count, 2) if count > 0 else None
    
    # Activity history (last N days)
    now = datetime.utcnow()
    start_date = (now - timedelta(days=days)).date()
    
    activity_data = db.query(
        func.date(AssignmentSubmission.graded_at).label('graded_date'),
        func.count(AssignmentSubmission.id).label('count')
    ).filter(
        AssignmentSubmission.assignment_id.in_(assignment_ids_query),
        AssignmentSubmission.graded_by == teacher_id,
        AssignmentSubmission.is_graded == True,
        AssignmentSubmission.graded_at >= start_date
    ).group_by(
        func.date(AssignmentSubmission.graded_at)
    ).all()
    
    activity_history = [
        ActivityHistoryItem(date=item.graded_date, submissions_graded=item.count)
        for item in activity_data
    ]
    
    # Total feedbacks
    total_feedbacks = db.query(func.count(AssignmentSubmission.id)).filter(
        AssignmentSubmission.assignment_id.in_(assignment_ids_query),
        AssignmentSubmission.graded_by == teacher_id,
        AssignmentSubmission.is_graded == True,
        AssignmentSubmission.feedback.isnot(None),
        AssignmentSubmission.feedback != ""
    ).scalar() or 0
    
    return TeacherDetailsResponse(
        teacher_id=teacher_id,
        teacher_name=teacher.name,
        email=teacher.email,
        avatar_url=teacher.avatar_url,
        groups_count=len(teacher_group_ids),
        students_count=students_count,
        grade_distribution=grade_distribution,
        activity_history=activity_history,
        total_feedbacks=total_feedbacks,
        avg_score_given=avg_score_given
    )


@router.get("/course/{course_id}/teacher/{teacher_id}/feedbacks", response_model=TeacherFeedbacksResponse)
async def get_teacher_feedbacks(
    course_id: int,
    teacher_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get paginated list of feedbacks given by a specific teacher.
    """
    # Authorization
    if current_user.role not in ["head_teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only Head Teachers and Admins can access this endpoint")
    
    if current_user.role == "head_teacher":
        access = db.query(CourseHeadTeacher).filter(
            CourseHeadTeacher.course_id == course_id,
            CourseHeadTeacher.head_teacher_id == current_user.id
        ).first()
        if not access:
            raise HTTPException(status_code=403, detail="You do not manage this course")
    
    teacher = db.query(UserInDB).filter(UserInDB.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    # Get groups for this teacher in this course
    group_accesses = db.query(CourseGroupAccess).filter(
        CourseGroupAccess.course_id == course_id,
        CourseGroupAccess.is_active == True
    ).all()
    group_ids = [ga.group_id for ga in group_accesses]
    
    teacher_group_ids = db.query(Group.id).filter(
        Group.id.in_(group_ids),
        Group.teacher_id == teacher_id
    ).all()
    teacher_group_ids = [g.id for g in teacher_group_ids]
    
    # Get assignments
    assignment_ids_query = db.query(Assignment.id).filter(
        Assignment.group_id.in_(teacher_group_ids),
        Assignment.is_active == True
    ).subquery()
    
    # Get feedbacks with student and assignment info
    feedbacks_query = db.query(
        AssignmentSubmission,
        UserInDB.name.label('student_name'),
        Assignment.title.label('assignment_title')
    ).join(
        UserInDB, UserInDB.id == AssignmentSubmission.user_id
    ).join(
        Assignment, Assignment.id == AssignmentSubmission.assignment_id
    ).filter(
        AssignmentSubmission.assignment_id.in_(assignment_ids_query),
        AssignmentSubmission.graded_by == teacher_id,
        AssignmentSubmission.is_graded == True,
        AssignmentSubmission.feedback.isnot(None),
        AssignmentSubmission.feedback != ""
    ).order_by(
        desc(AssignmentSubmission.graded_at)
    )
    
    total = feedbacks_query.count()
    feedbacks_data = feedbacks_query.offset(skip).limit(limit).all()
    
    feedbacks = [
        FeedbackItem(
            submission_id=item.AssignmentSubmission.id,
            student_name=item.student_name,
            assignment_title=item.assignment_title,
            score=item.AssignmentSubmission.score,
            max_score=item.AssignmentSubmission.max_score,
            feedback=item.AssignmentSubmission.feedback,
            graded_at=item.AssignmentSubmission.graded_at
        )
        for item in feedbacks_data
    ]
    
    return TeacherFeedbacksResponse(
        teacher_id=teacher_id,
        teacher_name=teacher.name,
        feedbacks=feedbacks,
        total=total
    )


@router.get("/course/{course_id}/teacher/{teacher_id}/assignments", response_model=TeacherAssignmentsResponse)
async def get_teacher_assignments(
    course_id: int,
    teacher_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get paginated list of assignments managed by a specific teacher in their groups.
    """
    # Authorization
    if current_user.role not in ["head_teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only Head Teachers and Admins can access this endpoint")
    
    if current_user.role == "head_teacher":
        access = db.query(CourseHeadTeacher).filter(
            CourseHeadTeacher.course_id == course_id,
            CourseHeadTeacher.head_teacher_id == current_user.id
        ).first()
        if not access:
            raise HTTPException(status_code=403, detail="You do not manage this course")
    
    teacher = db.query(UserInDB).filter(UserInDB.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    # Get groups for this teacher in this course
    group_accesses = db.query(CourseGroupAccess).filter(
        CourseGroupAccess.course_id == course_id,
        CourseGroupAccess.is_active == True
    ).all()
    group_ids = [ga.group_id for ga in group_accesses]
    
    teacher_groups = db.query(Group).filter(
        Group.id.in_(group_ids),
        Group.teacher_id == teacher_id
    ).all()
    teacher_group_ids = [g.id for g in teacher_groups]
    groups_map = {g.id: g.name for g in teacher_groups}
    
    # Get assignments
    assignments_query = db.query(Assignment).filter(
        Assignment.group_id.in_(teacher_group_ids),
        Assignment.is_active == True
    ).order_by(
        desc(Assignment.created_at)
    )
    
    total = assignments_query.count()
    assignments_data = assignments_query.offset(skip).limit(limit).all()
    
    assignments = []
    for assignment in assignments_data:
        # Count submissions
        total_submissions = db.query(func.count(AssignmentSubmission.id)).filter(
            AssignmentSubmission.assignment_id == assignment.id
        ).scalar() or 0
        
        graded_submissions = db.query(func.count(AssignmentSubmission.id)).filter(
            AssignmentSubmission.assignment_id == assignment.id,
            AssignmentSubmission.is_graded == True
        ).scalar() or 0
        
        assignments.append(AssignmentItem(
            assignment_id=assignment.id,
            title=assignment.title,
            group_name=groups_map.get(assignment.group_id, "Unknown"),
            due_date=assignment.due_date,
            total_submissions=total_submissions,
            graded_submissions=graded_submissions,
            created_at=assignment.created_at
        ))
    
    return TeacherAssignmentsResponse(
        teacher_id=teacher_id,
        teacher_name=teacher.name,
        assignments=assignments,
        total=total
    )

