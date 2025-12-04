from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, select
from typing import List, Optional, Dict, Any
from datetime import datetime
import json

from src.config import get_db
from src.schemas.models import (
    Assignment, AssignmentSubmission, Lesson, Module, Course, UserInDB,
    AssignmentSchema, AssignmentCreateSchema, AssignmentSubmissionSchema,
    SubmitAssignmentSchema, GradeSubmissionSchema
)
from src.routes.auth import get_current_user_dependency
from src.utils.permissions import require_teacher_or_admin, check_course_access
from src.utils.assignment_checker import check_assignment_answers

router = APIRouter()

# =============================================================================
# ASSIGNMENT MANAGEMENT
# =============================================================================

@router.get("/", response_model=List[AssignmentSchema])
async def get_assignments(
    lesson_id: Optional[str] = None,
    course_id: Optional[int] = None,
    group_id: Optional[int] = None,
    assignment_type: Optional[str] = None,
    is_active: Optional[bool] = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get assignments based on filters and user permissions"""
    query = db.query(Assignment)
    
    # Apply filters
    if lesson_id:
        try:
            lesson_id_int = int(lesson_id)
            query = query.filter(Assignment.lesson_id == lesson_id_int)
        except (ValueError, TypeError):
            # If lesson_id is not a valid integer, ignore it
            pass
    if group_id:
        query = query.filter(Assignment.group_id == group_id)
    if assignment_type:
        query = query.filter(Assignment.assignment_type == assignment_type)
    if is_active is not None:
        query = query.filter(Assignment.is_active == is_active)
    
    # Apply course filter and access control
    if course_id:
        # Get lessons in the course
        lesson_ids = db.query(Lesson.id).join(Module).filter(Module.course_id == course_id).subquery()
        query = query.filter(Assignment.lesson_id.in_(lesson_ids))
        
        # Check course access
        if not check_course_access(course_id, current_user, db):
            raise HTTPException(status_code=403, detail="Access denied to this course")
    elif current_user.role == "student":
        # Students see only assignments from their enrolled courses and groups
        from src.schemas.models import Enrollment, GroupStudent
        
        # Get enrolled course IDs
        enrolled_course_ids = db.query(Course.id).join(Enrollment).filter(
            Enrollment.user_id == current_user.id,
            Enrollment.is_active == True
        ).subquery()
        
        # Get lesson IDs from enrolled courses
        lesson_ids = db.query(Lesson.id).join(Module).filter(
            Module.course_id.in_(select(enrolled_course_ids))
        ).subquery()
        
        # Get group IDs where student is a member
        group_ids = db.query(GroupStudent.group_id).filter(
            GroupStudent.student_id == current_user.id
        ).subquery()
        
        # Filter assignments by lessons OR groups
        query = query.filter(
            (Assignment.lesson_id.in_(select(lesson_ids))) | (Assignment.group_id.in_(select(group_ids)))
        )
    elif current_user.role == "teacher":
        # Teachers see only assignments from their courses and groups
        teacher_course_ids = db.query(Course.id).filter(Course.teacher_id == current_user.id).subquery()
        lesson_ids = db.query(Lesson.id).join(Module).filter(
            Module.course_id.in_(teacher_course_ids)
        ).subquery()
        
        # Get group IDs where teacher is the teacher
        from src.schemas.models import Group
        teacher_group_ids = db.query(Group.id).filter(Group.teacher_id == current_user.id).subquery()
        
        # Filter assignments by lessons OR groups
        query = query.filter(
            (Assignment.lesson_id.in_(lesson_ids)) | (Assignment.group_id.in_(teacher_group_ids))
        )
    
    assignments = query.offset(skip).limit(limit).all()
    return [AssignmentSchema.from_orm(assignment) for assignment in assignments]

@router.post("/", response_model=AssignmentSchema)
async def create_assignment(
    assignment_data: AssignmentCreateSchema,
    lesson_id: Optional[int] = None,
    current_user: UserInDB = Depends(require_teacher_or_admin()),
    db: Session = Depends(get_db)
):
    """Create new assignment"""
    target_lesson_id = lesson_id
    
    # If lesson_id provided, check permissions
    if target_lesson_id:
        lesson = db.query(Lesson).filter(Lesson.id == target_lesson_id).first()
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")
        
        # Get course through module
        module = db.query(Module).filter(Module.id == lesson.module_id).first()
        course = db.query(Course).filter(Course.id == module.course_id).first()
        
        # Check permissions
        if current_user.role != "admin" and course.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # If group_id provided, check permissions
    if assignment_data.group_id:
        from src.schemas.models import Group
        group = db.query(Group).filter(Group.id == assignment_data.group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        
        # Check permissions
        if current_user.role != "admin" and group.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Validate assignment content based on type
    validate_assignment_content(assignment_data.assignment_type, assignment_data.content)
    
    # Validate due date
    if assignment_data.due_date and assignment_data.due_date < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Due date cannot be in the past")
        
    # Determine target groups
    target_group_ids = []
    if assignment_data.group_ids:
        target_group_ids = assignment_data.group_ids
    elif assignment_data.group_id:
        target_group_ids = [assignment_data.group_id]
        
    created_assignments = []
    
    # If we have target groups, create an assignment for each group
    if target_group_ids:
        for gid in target_group_ids:
            # Check permissions for each group
            from src.schemas.models import Group
            group = db.query(Group).filter(Group.id == gid).first()
            if not group:
                continue # Skip invalid groups or raise error?
            
            if current_user.role != "admin" and group.teacher_id != current_user.id:
                raise HTTPException(status_code=403, detail=f"Access denied to group {gid}")
                
            new_assignment = Assignment(
                lesson_id=target_lesson_id,
                group_id=gid,
                title=assignment_data.title,
                description=assignment_data.description,
                assignment_type=assignment_data.assignment_type,
                content=json.dumps(assignment_data.content),
                correct_answers=json.dumps(assignment_data.correct_answers) if assignment_data.correct_answers else None,
                max_score=assignment_data.max_score,
                time_limit_minutes=assignment_data.time_limit_minutes if hasattr(assignment_data, 'time_limit_minutes') else None,
                due_date=assignment_data.due_date,
                allowed_file_types=assignment_data.allowed_file_types,
                max_file_size_mb=assignment_data.max_file_size_mb
            )
            db.add(new_assignment)
            created_assignments.append(new_assignment)
            
    else:
        # Create single assignment (e.g. lesson-only or no group)
        new_assignment = Assignment(
            lesson_id=target_lesson_id,
            group_id=None,
            title=assignment_data.title,
            description=assignment_data.description,
            assignment_type=assignment_data.assignment_type,
            content=json.dumps(assignment_data.content),
            correct_answers=json.dumps(assignment_data.correct_answers) if assignment_data.correct_answers else None,
            max_score=assignment_data.max_score,
            time_limit_minutes=assignment_data.time_limit_minutes if hasattr(assignment_data, 'time_limit_minutes') else None,
            due_date=assignment_data.due_date,
            allowed_file_types=assignment_data.allowed_file_types,
            max_file_size_mb=assignment_data.max_file_size_mb
        )
        db.add(new_assignment)
        created_assignments.append(new_assignment)
    
    db.commit()
    
    # Refresh all created assignments
    for a in created_assignments:
        db.refresh(a)
    
    # Return the first one to satisfy response model
    return AssignmentSchema.from_orm(created_assignments[0])

@router.get("/{assignment_id}", response_model=AssignmentSchema)
async def get_assignment(
    assignment_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get assignment details"""
    
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    
    # Check access permissions
    has_access = False
    
    # Check course access if assignment is linked to lesson
    if assignment.lesson_id:
        lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
        if lesson:
            module = db.query(Module).filter(Module.id == lesson.module_id).first()
            if module and check_course_access(module.course_id, current_user, db):
                has_access = True
                print(f"Access granted via course: {module.course_id}")
    
    # Check group access if assignment is linked to group
    if assignment.group_id:
        from src.schemas.models import Group, GroupStudent
        
        if current_user.role == "admin":
            has_access = True
            print("Access granted via admin role")
        elif current_user.role == "teacher":
            group = db.query(Group).filter(Group.id == assignment.group_id).first()
            if group and group.teacher_id == current_user.id:
                has_access = True
                print(f"Access granted via teacher role for group: {assignment.group_id}")
        elif current_user.role == "student":
            group_member = db.query(GroupStudent).filter(
                GroupStudent.group_id == assignment.group_id,
                GroupStudent.student_id == current_user.id
            ).first()
            if group_member:
                has_access = True
                print(f"Access granted via student role for group: {assignment.group_id}")
    
    if not has_access:
        print(f"Access denied for user {current_user.id} to assignment {assignment_id}")
        raise HTTPException(status_code=403, detail="Access denied to this assignment")
    
    print(f"Access granted, returning assignment data")
    
    assignment_data = AssignmentSchema.from_orm(assignment)
    
    # Hide correct answers from students
    if current_user.role == "student":
        assignment_data.content = remove_correct_answers_from_content(assignment_data.content)
    
    return assignment_data

@router.put("/{assignment_id}", response_model=AssignmentSchema)
async def update_assignment(
    assignment_id: int,
    assignment_data: AssignmentCreateSchema,
    current_user: UserInDB = Depends(require_teacher_or_admin()),
    db: Session = Depends(get_db)
):
    """Update assignment"""
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Check permissions if assignment is linked to lesson
    if assignment.lesson_id:
        lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
        module = db.query(Module).filter(Module.id == lesson.module_id).first()
        course = db.query(Course).filter(Course.id == module.course_id).first()
        
        if current_user.role != "admin" and course.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Check permissions if assignment is linked to group
    if assignment.group_id:
        from src.schemas.models import Group
        group = db.query(Group).filter(Group.id == assignment.group_id).first()
        if current_user.role != "admin" and group.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Validate content
    validate_assignment_content(assignment_data.assignment_type, assignment_data.content)
    
    # Validate due date
    if assignment_data.due_date and assignment_data.due_date < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Due date cannot be in the past")
    
    # Update fields
    assignment.title = assignment_data.title
    assignment.description = assignment_data.description
    assignment.assignment_type = assignment_data.assignment_type
    assignment.content = json.dumps(assignment_data.content)
    assignment.correct_answers = json.dumps(assignment_data.correct_answers) if assignment_data.correct_answers else None
    assignment.max_score = assignment_data.max_score
    assignment.time_limit_minutes = assignment_data.time_limit_minutes
    assignment.due_date = assignment_data.due_date
    assignment.group_id = assignment_data.group_id
    assignment.allowed_file_types = assignment_data.allowed_file_types
    assignment.max_file_size_mb = assignment_data.max_file_size_mb
    
    db.commit()
    db.refresh(assignment)
    
    return AssignmentSchema.from_orm(assignment)

@router.delete("/{assignment_id}")
async def delete_assignment(
    assignment_id: int,
    current_user: UserInDB = Depends(require_teacher_or_admin()),
    db: Session = Depends(get_db)
):
    """Delete assignment"""
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Check permissions
    if assignment.lesson_id:
        lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
        module = db.query(Module).filter(Module.id == lesson.module_id).first()
        course = db.query(Course).filter(Course.id == module.course_id).first()
        
        if current_user.role != "admin" and course.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Soft delete
    assignment.is_active = False
    db.commit()
    
    return {"detail": "Assignment deleted successfully"}

# =============================================================================
# ASSIGNMENT SUBMISSIONS
# =============================================================================

@router.post("/{assignment_id}/submit", response_model=AssignmentSubmissionSchema)
async def submit_assignment(
    assignment_id: int,
    submission_data: SubmitAssignmentSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Submit assignment answers (students only)"""
    print(f"Submit assignment called: assignment_id={assignment_id}, user_id={current_user.id}")
    
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can submit assignments")
    
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    print(f"Assignment found: {assignment.title}, lesson_id={assignment.lesson_id}, group_id={assignment.group_id}")
    
    # Check if student has access to this assignment
    has_access = False
    
    # Check course access if assignment is linked to lesson
    if assignment.lesson_id:
        lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
        if lesson:
            module = db.query(Module).filter(Module.id == lesson.module_id).first()
            if module and check_course_access(module.course_id, current_user, db):
                has_access = True
                print(f"Access granted via course: {module.course_id}")
    
    # Check group access if assignment is linked to group
    if assignment.group_id:
        from src.schemas.models import GroupStudent
        group_member = db.query(GroupStudent).filter(
            GroupStudent.group_id == assignment.group_id,
            GroupStudent.student_id == current_user.id
        ).first()
        if group_member:
            has_access = True
            print(f"Access granted via group: {assignment.group_id}")
    
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied to this assignment")
    
    # Check if assignment is overdue
    if assignment.due_date and assignment.due_date < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Assignment deadline has passed")
    
    # Check if already submitted
    existing_submission = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id == assignment_id,
        AssignmentSubmission.user_id == current_user.id
    ).first()
    
    print(f"Checking for existing submissions: assignment_id={assignment_id}, user_id={current_user.id}")
    print(f"Existing submission found: {existing_submission is not None}")
    
    if existing_submission:
        print(f"Found existing submission: ID={existing_submission.id}, submitted_at={existing_submission.submitted_at}")
        print(f"Existing submission data: answers={existing_submission.answers}, file_url={existing_submission.file_url}")
        raise HTTPException(status_code=400, detail="Assignment already submitted")
    
    print(f"Creating submission with data: {submission_data}")
    print(f"Submission answers: {submission_data.answers}")
    print(f"Submission file_url: {submission_data.file_url}")
    print(f"Submission submitted_file_name: {submission_data.submitted_file_name}")
    
    # Auto-grade the assignment
    score = None
    # Skip auto-grading for multi_task assignments to allow manual grading
    if assignment.correct_answers and assignment.assignment_type != 'multi_task':
        try:
            correct_answers = json.loads(assignment.correct_answers)
            score = check_assignment_answers(
                assignment.assignment_type,
                submission_data.answers,
                correct_answers,
                assignment.max_score
            )
        except Exception as e:
            # If auto-grading fails, mark as ungraded
            score = None
            print(f"Auto-grading failed: {e}")
    
    # Create submission
    submission = AssignmentSubmission(
        assignment_id=assignment_id,
        user_id=current_user.id,
        answers=json.dumps(submission_data.answers),
        file_url=submission_data.file_url,
        submitted_file_name=submission_data.submitted_file_name,
        score=score,
        max_score=assignment.max_score,
        is_graded=score is not None,
        graded_at=datetime.utcnow() if score is not None else None
    )
    
    db.add(submission)
    db.commit()
    db.refresh(submission)
    
    print(f"Submission created successfully: {submission.id}")
    
    # Update student progress (only if assignment is linked to a lesson)
    if assignment.lesson_id:
        update_student_progress(assignment, current_user.id, score, db)
    
    return AssignmentSubmissionSchema.from_orm(submission)


@router.get("/{assignment_id}/debug-submissions")
async def debug_submissions(
    assignment_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Debug endpoint to check submissions for an assignment"""
    submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id == assignment_id,
        AssignmentSubmission.user_id == current_user.id
    ).all()
    
    return {
        "assignment_id": assignment_id,
        "user_id": current_user.id,
        "submissions_count": len(submissions),
        "submissions": [
            {
                "id": s.id,
                "submitted_at": s.submitted_at,
                "answers": s.answers,
                "file_url": s.file_url,
                "submitted_file_name": s.submitted_file_name
            }
            for s in submissions
        ]
    }


@router.delete("/{assignment_id}/debug-delete-submission/{submission_id}")
async def debug_delete_submission(
    assignment_id: int,
    submission_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Debug endpoint to delete a submission (for testing purposes)"""
    submission = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.id == submission_id,
        AssignmentSubmission.assignment_id == assignment_id,
        AssignmentSubmission.user_id == current_user.id
    ).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    db.delete(submission)
    db.commit()
    
    return {"message": f"Submission {submission_id} deleted successfully"}

@router.get("/{assignment_id}/submissions", response_model=List[AssignmentSubmissionSchema])
async def get_assignment_submissions(
    assignment_id: int,
    user_id: Optional[int] = None,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get submissions for assignment"""
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Check permissions
    if current_user.role == "student":
        # Students can only see their own submissions
        user_id = current_user.id
    elif current_user.role in ["teacher", "curator"]:
        # Teachers/curators can see submissions from their students
        if assignment.lesson_id:
            lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
            module = db.query(Module).filter(Module.id == lesson.module_id).first()
            
            if not check_course_access(module.course_id, current_user, db):
                raise HTTPException(status_code=403, detail="Access denied")
        elif assignment.group_id:
            from src.schemas.models import Group
            group = db.query(Group).filter(Group.id == assignment.group_id).first()
            if current_user.role != "admin" and group.teacher_id != current_user.id:
                raise HTTPException(status_code=403, detail="Access denied")
    
    query = db.query(AssignmentSubmission).filter(AssignmentSubmission.assignment_id == assignment_id)
    
    if user_id:
        query = query.filter(AssignmentSubmission.user_id == user_id)
    
    submissions = query.order_by(desc(AssignmentSubmission.submitted_at)).all()
    
    # Enhance submissions with user and grader names
    result = []
    for submission in submissions:
        submission_data = AssignmentSubmissionSchema.from_orm(submission)
        
        # Get user name
        user = db.query(UserInDB).filter(UserInDB.id == submission.user_id).first()
        if user:
            submission_data.user_name = user.name
        
        # Get grader name
        if submission.graded_by:
            grader = db.query(UserInDB).filter(UserInDB.id == submission.graded_by).first()
            if grader:
                submission_data.grader_name = grader.name
        
        result.append(submission_data)
    
    return result

@router.get("/submissions/my", response_model=List[AssignmentSubmissionSchema])
async def get_my_submissions(
    course_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get current user's assignment submissions"""
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can access this endpoint")
    
    query = db.query(AssignmentSubmission).filter(AssignmentSubmission.user_id == current_user.id)
    
    # Filter by course if specified
    if course_id:
        # Get assignment IDs for the course
        lesson_ids = db.query(Lesson.id).join(Module).filter(Module.course_id == course_id).subquery()
        assignment_ids = db.query(Assignment.id).filter(Assignment.lesson_id.in_(lesson_ids)).subquery()
        query = query.filter(AssignmentSubmission.assignment_id.in_(assignment_ids))
    
    submissions = query.order_by(desc(AssignmentSubmission.submitted_at)).offset(skip).limit(limit).all()
    return [AssignmentSubmissionSchema.from_orm(submission) for submission in submissions]

@router.put("/{assignment_id}/submissions/{submission_id}/grade", response_model=AssignmentSubmissionSchema)
async def grade_submission(
    assignment_id: int,
    submission_id: int,
    grade_data: GradeSubmissionSchema,
    current_user: UserInDB = Depends(require_teacher_or_admin()),
    db: Session = Depends(get_db)
):
    """Grade a submission (teachers only)"""
    # Check if assignment exists
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Check if submission exists
    submission = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.id == submission_id,
        AssignmentSubmission.assignment_id == assignment_id
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Check permissions
    has_access = False
    
    # Check course access if assignment is linked to lesson
    if assignment.lesson_id:
        lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
        if lesson:
            module = db.query(Module).filter(Module.id == lesson.module_id).first()
            if module and check_course_access(module.course_id, current_user, db):
                has_access = True
    
    # Check group access if assignment is linked to group
    if assignment.group_id:
        from src.schemas.models import Group
        group = db.query(Group).filter(Group.id == assignment.group_id).first()
        if current_user.role == "admin" or (group and group.teacher_id == current_user.id):
            has_access = True
    
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied to this assignment")
    
    # Validate score
    if grade_data.score < 0 or grade_data.score > assignment.max_score:
        raise HTTPException(
            status_code=400, 
            detail=f"Score must be between 0 and {assignment.max_score}"
        )
    
    # Update submission
    submission.score = grade_data.score
    submission.feedback = grade_data.feedback
    submission.graded_by = current_user.id
    submission.is_graded = True
    submission.graded_at = datetime.utcnow()
    
    db.commit()
    db.refresh(submission)
    
    # Enhance submission with names
    submission_data = AssignmentSubmissionSchema.from_orm(submission)
    
    # Get user name
    user = db.query(UserInDB).filter(UserInDB.id == submission.user_id).first()
    if user:
        submission_data.user_name = user.name
    
    # Get grader name
    submission_data.grader_name = current_user.name
    
    return submission_data

# =============================================================================
# ASSIGNMENT STATUS
# =============================================================================

@router.get("/{assignment_id}/student-progress", response_model=Dict[str, Any])
async def get_assignment_student_progress(
    assignment_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get student progress for an assignment (teachers only)"""
    if current_user.role not in ["teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only teachers and admins can access student progress")
    
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Check permissions
    has_access = False
    
    # Check course access if assignment is linked to lesson
    if assignment.lesson_id:
        lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
        if lesson:
            module = db.query(Module).filter(Module.id == lesson.module_id).first()
            if module and check_course_access(module.course_id, current_user, db):
                has_access = True
    
    # Check group access if assignment is linked to group
    if assignment.group_id:
        from src.schemas.models import Group
        group = db.query(Group).filter(Group.id == assignment.group_id).first()
        if current_user.role == "admin" or (group and group.teacher_id == current_user.id):
            has_access = True
    
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied to this assignment")
    
    # Get students who should have access to this assignment
    students = []
    assignment_sources = {}  # Track how each student got access to the assignment
    
    if assignment.lesson_id:
        # Course-based assignment - get enrolled students
        lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
        if lesson:
            module = db.query(Module).filter(Module.id == lesson.module_id).first()
            if module:
                enrolled_students = db.query(UserInDB).join(Enrollment).filter(
                    Enrollment.course_id == module.course_id,
                    Enrollment.is_active == True,
                    UserInDB.role == "student"
                ).all()
                
                for student in enrolled_students:
                    students.append(student)
                    assignment_sources[student.id] = "course"
        
    if assignment.group_id:
        # Group-based assignment - get group members
        from src.schemas.models import GroupStudent
        group_students = db.query(UserInDB).join(GroupStudent).filter(
            GroupStudent.group_id == assignment.group_id,
            UserInDB.role == "student"
        ).all()
        
        for student in group_students:
            if student.id in assignment_sources:
                # Student is both in course and group
                assignment_sources[student.id] = "both"
            else:
                students.append(student)
                assignment_sources[student.id] = "group"
    
    # If no lesson_id or group_id, this might be a standalone assignment
    # In this case, we need to determine who should see it
    if not assignment.lesson_id and not assignment.group_id:
        # For standalone assignments, we might need to check if there's a specific assignment assignment table
        # For now, we'll return empty list as these assignments need explicit assignment
        pass
    
    # Remove duplicates (in case a student is both enrolled and in group)
    unique_students = []
    seen_ids = set()
    for student in students:
        if student.id not in seen_ids:
            unique_students.append(student)
            seen_ids.add(student.id)
    
    # Get all submissions for this assignment
    submissions = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id == assignment_id
    ).all()
    
    # Create submission lookup
    submission_lookup = {sub.user_id: sub for sub in submissions}
    
    # Build student progress data
    student_progress = []
    for student in unique_students:
        submission = submission_lookup.get(student.id)
        
        # Determine status
        status = "not_submitted"
        score = None
        submitted_at = None
        graded_at = None
        is_overdue = False
        
        if submission:
            if submission.is_graded and submission.score is not None:
                status = "graded"
                score = submission.score
                graded_at = submission.graded_at
            else:
                status = "submitted"
            submitted_at = submission.submitted_at
        else:
            # Check if overdue
            if assignment.due_date and assignment.due_date < datetime.utcnow():
                status = "overdue"
                is_overdue = True
        
        # Get assignment source information
        assignment_source = assignment_sources.get(student.id, "unknown")
        source_display = {
            "course": "Course Enrollment",
            "group": "Group Membership", 
            "both": "Course & Group",
            "unknown": "Unknown"
        }.get(assignment_source, "Unknown")
        
        student_progress.append({
            "id": student.id,
            "name": student.name,
            "email": student.email,
            "status": status,
            "submission_id": submission.id if submission else None,
            "score": score,
            "max_score": assignment.max_score,
            "submitted_at": submitted_at,
            "graded_at": graded_at,
            "is_overdue": is_overdue,
            "assignment_source": assignment_source,
            "source_display": source_display
        })
    
    # Sort by name
    student_progress.sort(key=lambda x: x["name"])
    
    # Calculate summary stats
    total_students = len(student_progress)
    not_submitted = len([s for s in student_progress if s["status"] == "not_submitted"])
    submitted = len([s for s in student_progress if s["status"] == "submitted"])
    graded = len([s for s in student_progress if s["status"] == "graded"])
    overdue = len([s for s in student_progress if s["status"] == "overdue"])
    
    # Calculate source breakdown
    source_breakdown = {}
    for student in student_progress:
        source = student["assignment_source"]
        source_breakdown[source] = source_breakdown.get(source, 0) + 1
    
    return {
        "assignment": {
            "id": assignment.id,
            "title": assignment.title,
            "description": assignment.description,
            "due_date": assignment.due_date,
            "max_score": assignment.max_score,
            "lesson_id": assignment.lesson_id,
            "group_id": assignment.group_id,
            "assignment_type": assignment.assignment_type,
            "content": json.loads(assignment.content) if isinstance(assignment.content, str) else assignment.content
        },
        "students": student_progress,
        "summary": {
            "total_students": total_students,
            "not_submitted": not_submitted,
            "submitted": submitted,
            "graded": graded,
            "overdue": overdue
        },
        "source_breakdown": source_breakdown
    }

@router.get("/{assignment_id}/status", response_model=Dict[str, Any])
async def get_assignment_status_for_student(
    assignment_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get assignment status for current student"""
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can access assignment status")
    
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Check if student has access to this assignment
    has_access = False
    
    # Check course access if assignment is linked to lesson
    if assignment.lesson_id:
        lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
        if lesson:
            module = db.query(Module).filter(Module.id == lesson.module_id).first()
            if module and check_course_access(module.course_id, current_user, db):
                has_access = True
    
    # Check group access if assignment is linked to group
    if assignment.group_id:
        from src.schemas.models import GroupStudent
        group_member = db.query(GroupStudent).filter(
            GroupStudent.group_id == assignment.group_id,
            GroupStudent.student_id == current_user.id
        ).first()
        if group_member:
            has_access = True
    
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied to this assignment")
    
    # Get existing submission
    submission = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id == assignment_id,
        AssignmentSubmission.user_id == current_user.id
    ).first()
    
    # Determine status
    status = "not_started"
    attempts_left = 1  # async default to 1 attempt
    late = False
    
    if submission:
        if submission.is_graded:
            status = "graded"
        else:
            status = "submitted"
        attempts_left = 0  # Already submitted
    else:
        # Check if assignment is overdue
        if assignment.due_date and assignment.due_date < datetime.utcnow():
            late = True
            status = "overdue"
    
    return {
        "status": status,
        "attempts_left": attempts_left,
        "late": late,
        "due_date": assignment.due_date,
        "submitted_at": submission.submitted_at if submission else None,
        "score": submission.score if submission else None,
        "max_score": assignment.max_score,
        # Include submission details for displaying student's answers
        "submission_id": submission.id if submission else None,
        "answers": json.loads(submission.answers) if submission and submission.answers else None,
        "file_url": submission.file_url if submission else None,
        "submitted_file_name": submission.submitted_file_name if submission else None,
        "feedback": submission.feedback if submission else None
    }

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def validate_assignment_content(assignment_type: str, content: Dict[str, Any]):
    """Validate assignment content based on type"""
    required_fields = {
        "single_choice": ["question", "options"],
        "multiple_choice": ["question", "options"],
        "picture_choice": ["question", "images"],
        "fill_in_blanks": ["text_with_blanks"],
        "matching": ["left_items", "right_items"],
        "matching_text": ["items_to_match"],
        "free_text": ["question"],
        "file_upload": ["question", "allowed_file_types"],
        "multi_task": ["tasks"]  # Multi-task assignment
    }
    
    if assignment_type not in required_fields:
        raise HTTPException(status_code=400, detail=f"Unsupported assignment type: {assignment_type}")
    
    # Validate required fields for the assignment type
    for field in required_fields[assignment_type]:
        if field not in content:
            raise HTTPException(status_code=400, detail=f"Missing required field '{field}' for {assignment_type}")
    
    # Additional validation for multi-task assignments
    if assignment_type == "multi_task":
        tasks = content.get("tasks", [])
        if not isinstance(tasks, list) or len(tasks) == 0:
            raise HTTPException(status_code=400, detail="multi_task assignment must have at least one task")
        
        # Validate each task
        valid_task_types = ["course_unit", "file_task", "text_task", "link_task"]
        for i, task in enumerate(tasks):
            # Check required task fields
            if not isinstance(task, dict):
                raise HTTPException(status_code=400, detail=f"Task {i+1} must be an object")
            
            required_task_fields = ["id", "task_type", "title", "order_index", "points", "content"]
            for field in required_task_fields:
                if field not in task:
                    raise HTTPException(status_code=400, detail=f"Task {i+1} missing required field '{field}'")
            
            # Validate task type
            task_type = task.get("task_type")
            if task_type not in valid_task_types:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Task {i+1} has invalid task_type '{task_type}'. Must be one of: {', '.join(valid_task_types)}"
                )
            
            # Validate task-specific content
            task_content = task.get("content", {})
            if task_type == "course_unit":
                if "course_id" not in task_content or "lesson_ids" not in task_content:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Task {i+1} (course_unit) must have 'course_id' and 'lesson_ids' in content"
                    )
            elif task_type == "file_task":
                if "question" not in task_content:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Task {i+1} (file_task) must have 'question' in content"
                    )
            elif task_type == "text_task":
                if "question" not in task_content:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Task {i+1} (text_task) must have 'question' in content"
                    )
            elif task_type == "link_task":
                if "url" not in task_content:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Task {i+1} (link_task) must have 'url' in content"
                    )


def remove_correct_answers_from_content(content: Dict[str, Any]) -> Dict[str, Any]:
    """Remove correct answers from content when showing to students"""
    # Make a copy to avoid modifying original
    clean_content = content.copy()
    
    # Remove fields that might contain answers
    fields_to_remove = ["correct_answer", "correct_answers", "answer_key"]
    for field in fields_to_remove:
        if field in clean_content:
            del clean_content[field]
    
    # Handle multi-task assignments - remove answers from each task
    if "tasks" in clean_content and isinstance(clean_content["tasks"], list):
        clean_tasks = []
        for task in clean_content["tasks"]:
            if isinstance(task, dict):
                clean_task = task.copy()
                # Remove answer fields from task content
                if "content" in clean_task and isinstance(clean_task["content"], dict):
                    task_content = clean_task["content"].copy()
                    for field in fields_to_remove:
                        if field in task_content:
                            del task_content[field]
                    clean_task["content"] = task_content
                clean_tasks.append(clean_task)
            else:
                clean_tasks.append(task)
        clean_content["tasks"] = clean_tasks
    
    return clean_content

def update_student_progress(assignment: Assignment, user_id: int, score: Optional[int], db: Session):
    """Update student progress after assignment submission"""
    if not assignment.lesson_id:
        return
    
    lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
    module = db.query(Module).filter(Module.id == lesson.module_id).first()
    
    # Find or create progress record
    from src.schemas.models import StudentProgress
    progress = db.query(StudentProgress).filter(
        StudentProgress.user_id == user_id,
        StudentProgress.course_id == module.course_id,
        StudentProgress.assignment_id == assignment.id
    ).first()
    
    if not progress:
        progress = StudentProgress(
            user_id=user_id,
            course_id=module.course_id,
            lesson_id=assignment.lesson_id,
            assignment_id=assignment.id,
            status="completed" if score is not None else "in_progress",
            completion_percentage=100 if score is not None and score >= (assignment.max_score * 0.6) else 50,
            last_accessed=datetime.utcnow(),
            completed_at=datetime.utcnow() if score is not None else None
        )
        db.add(progress)
    else:
        progress.status = "completed" if score is not None else "in_progress"
        progress.completion_percentage = 100 if score is not None and score >= (assignment.max_score * 0.6) else 50
        progress.last_accessed = datetime.utcnow()
        if score is not None:
            progress.completed_at = datetime.utcnow()
    
    db.commit()

# =============================================================================
# ASSIGNMENT TYPES INFO
# =============================================================================

@router.get("/types")
async def get_assignment_types():
    """Get supported assignment types and their schemas"""
    return {
        "supported_types": [
            {
                "type": "single_choice",
                "name": "Single Choice",
                "description": "Выбор одного правильного ответа из нескольких вариантов",
                "schema": {
                    "question": "str",
                    "options": ["str"],
                    "correct_answer": "int (index)"
                }
            },
            {
                "type": "multiple_choice",
                "name": "Multiple Choice", 
                "description": "Выбор нескольких правильных ответов",
                "schema": {
                    "question": "str",
                    "options": ["str"],
                    "correct_answers": ["int (indices)"]
                }
            },
            {
                "type": "picture_choice",
                "name": "Picture Choice",
                "description": "Выбор из изображений",
                "schema": {
                    "question": "str",
                    "images": [{"url": "str", "caption": "str"}],
                    "correct_answer": "int (index)"
                }
            },
            {
                "type": "fill_in_blanks",
                "name": "Fill in the Blanks",
                "description": "Заполнение пропусков в тексте",
                "schema": {
                    "text_with_blanks": "str (with _____ for blanks)",
                    "correct_answers": ["str"]
                }
            },
            {
                "type": "matching",
                "name": "Matching",
                "description": "Сопоставление элементов",
                "schema": {
                    "left_items": ["str"],
                    "right_items": ["str"],
                    "correct_matches": {"left_index": "right_index"}
                }
            },
            {
                "type": "matching_text",
                "name": "Matching Text",
                "description": "Сопоставление текстовых элементов",
                "schema": {
                    "items_to_match": [{"term": "str", "async definition": "str"}],
                    "shuffle": "bool"
                }
            },
            {
                "type": "free_text",
                "name": "Free Text",
                "description": "Свободный ответ текстом",
                "schema": {
                    "question": "str",
                    "max_length": "int (optional)",
                    "keywords": ["str (for auto-checking)"]
                }
            },
            {
                "type": "file_upload",
                "name": "File Upload",
                "description": "Загрузка файла",
                "schema": {
                    "question": "str",
                    "allowed_file_types": ["str"],
                    "max_file_size_mb": "int"
                }
            },
            {
                "type": "multi_task",
                "name": "Multi-Task Homework",
                "description": "Домашнее задание с несколькими задачами разных типов",
                "schema": {
                    "tasks": [{
                        "id": "str",
                        "task_type": "str (course_unit, file_task, text_task, link_task)",
                        "title": "str",
                        "description": "str (optional)",
                        "order_index": "int",
                        "points": "int",
                        "content": "dict (task-specific)"
                    }],
                    "total_points": "int",
                    "instructions": "str (optional)"
                }
            }
        ]
    }
