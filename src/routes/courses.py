from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
from typing import List, Optional
import os
import uuid
from datetime import datetime
import aiofiles

from src.config import get_db
from src.schemas.models import (
    Course, Module, Lesson, Step, LessonMaterial, Enrollment, StudentProgress,
    CourseSchema, CourseCreateSchema, ModuleSchema, ModuleCreateSchema,
    LessonSchema, LessonCreateSchema, StepSchema, StepCreateSchema,
    LessonMaterialSchema, UserInDB, QuizData,
    CourseGroupAccess, CourseGroupAccessSchema, Group, GroupStudent,
    LegacyLessonSchema  # Keep for migration period
)
from src.routes.auth import get_current_user_dependency
from src.utils.permissions import require_teacher_or_admin, require_admin, check_course_access
from src.services.azure_openai_service import AzureOpenAIService
from src.utils.duration_calculator import update_course_duration

router = APIRouter()

# =============================================================================
# COURSE MANAGEMENT
# =============================================================================

@router.get("/", response_model=List[CourseSchema])
async def get_courses(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    teacher_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get list of courses based on user role and permissions"""
    # Base query – role-specific filters applied below
    query = db.query(Course)
    
    if current_user.role == "student":
        # Students see courses they are enrolled in OR courses their group has access to
        from src.schemas.models import GroupStudent, CourseGroupAccess
        
        # Get enrolled course IDs
        enrolled_course_ids = db.query(Enrollment.course_id).filter(
            Enrollment.user_id == current_user.id,
            Enrollment.is_active == True
        ).subquery()
        
        # Get group access course IDs
        group_student = db.query(GroupStudent).filter(
            GroupStudent.student_id == current_user.id
        ).first()
        
        group_course_ids = None
        if group_student:
            group_course_ids = db.query(CourseGroupAccess.course_id).filter(
                CourseGroupAccess.group_id == group_student.group_id,
                CourseGroupAccess.is_active == True
            ).subquery()
        
        # Combine both sets of course IDs
        if group_course_ids is not None:
            # Use UNION to combine both queries
            from sqlalchemy import union
            combined_course_ids = db.query(union(
                enrolled_course_ids.select(),
                group_course_ids.select()
            ).alias('course_id')).subquery()
            query = query.filter(Course.id.in_(combined_course_ids), Course.is_active == True)
        else:
            # Only enrolled courses
            query = query.filter(Course.id.in_(enrolled_course_ids), Course.is_active == True)
        
    elif current_user.role == "teacher":
        # Teachers see their own courses (both active and drafts)
        query = query.filter(Course.teacher_id == current_user.id)
        
    elif current_user.role == "curator":
        # Curators: for now, show active courses only
        query = query.filter(Course.is_active == True)
    
    # Apply filters
    if teacher_id is not None:
        query = query.filter(Course.teacher_id == teacher_id)
    if is_active is not None:
        query = query.filter(Course.is_active == is_active)
    
    courses = query.offset(skip).limit(limit).all()
    
    # Enrich with teacher names and module counts
    courses_data = []
    for course in courses:
        teacher = db.query(UserInDB).filter(UserInDB.id == course.teacher_id).first()
        module_count = db.query(Module).filter(Module.course_id == course.id).count()
        
        course_data = CourseSchema.from_orm(course)
        course_data.teacher_name = teacher.name if teacher else "Unknown"
        course_data.total_modules = module_count
        # Map is_active to user-friendly status for frontend (draft/active)
        course_data.status = 'active' if course.is_active else 'draft'
        courses_data.append(course_data)
    
    return courses_data

@router.get("/my-courses", response_model=List[CourseSchema])
async def get_my_courses(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get student's enrolled courses with basic info"""
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can access this endpoint")
    
    # Get enrolled course IDs
    enrolled_course_ids = db.query(Enrollment.course_id).filter(
        Enrollment.user_id == current_user.id,
        Enrollment.is_active == True
    ).subquery()
    
    # Get group access course IDs
    group_student = db.query(GroupStudent).filter(
        GroupStudent.student_id == current_user.id
    ).first()
    
    group_course_ids = None
    if group_student:
        group_course_ids = db.query(CourseGroupAccess.course_id).filter(
            CourseGroupAccess.group_id == group_student.group_id,
            CourseGroupAccess.is_active == True
        ).subquery()
    
    # Combine both sets of course IDs
    if group_course_ids is not None:
        # Use UNION to combine both queries
        from sqlalchemy import union
        combined_course_ids = db.query(union(
            enrolled_course_ids.select(),
            group_course_ids.select()
        ).alias('course_id')).subquery()
        courses = db.query(Course).filter(
            Course.id.in_(combined_course_ids), 
            Course.is_active == True
        ).all()
    else:
        # Only enrolled courses
        courses = db.query(Course).filter(
            Course.id.in_(enrolled_course_ids), 
            Course.is_active == True
        ).all()
    
    # Enrich with teacher names and module counts
    courses_data = []
    for course in courses:
        teacher = db.query(UserInDB).filter(UserInDB.id == course.teacher_id).first()
        module_count = db.query(Module).filter(Module.course_id == course.id).count()
        
        course_data = CourseSchema.from_orm(course)
        course_data.teacher_name = teacher.name if teacher else "Unknown"
        course_data.total_modules = module_count
        course_data.status = 'active' if course.is_active else 'draft'
        courses_data.append(course_data)
    
    return courses_data

@router.post("/", response_model=CourseSchema)
async def create_course(
    course_data: CourseCreateSchema,
    current_user: UserInDB = Depends(require_teacher_or_admin()),
    db: Session = Depends(get_db)
):
    """Create new course (teachers and admins only)"""
    # If admin is creating course, allow assigning teacher explicitly
    teacher_id = current_user.id
    if current_user.role == "admin" and getattr(course_data, 'teacher_id', None):
        teacher_id = course_data.teacher_id
    
    new_course = Course(
        title=course_data.title,
        description=course_data.description,
        cover_image_url=course_data.cover_image_url,
        teacher_id=teacher_id,
        estimated_duration_minutes=course_data.estimated_duration_minutes
    )
    
    db.add(new_course)
    db.commit()
    db.refresh(new_course)
    
    # Create response with teacher name
    teacher = db.query(UserInDB).filter(UserInDB.id == teacher_id).first()
    course_response = CourseSchema.from_orm(new_course)
    course_response.teacher_name = teacher.name if teacher else "Unknown"
    course_response.total_modules = 0
    course_response.status = 'active' if new_course.is_active else 'draft'
    
    return course_response

@router.get("/{course_id}", response_model=CourseSchema)
async def get_course(
    course_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get course details"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check access permissions
    if not check_course_access(course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this course")
    
    # Get teacher info and module count
    teacher = db.query(UserInDB).filter(UserInDB.id == course.teacher_id).first()
    module_count = db.query(Module).filter(Module.course_id == course.id).count()
    
    # Auto-recalculate duration if it's 0 or not set
    if course.estimated_duration_minutes == 0:
        update_course_duration(course.id, db)
        db.refresh(course)
    
    course_response = CourseSchema.from_orm(course)
    course_response.teacher_name = teacher.name if teacher else "Unknown"
    course_response.total_modules = module_count
    course_response.status = 'active' if course.is_active else 'draft'
    
    return course_response

@router.put("/{course_id}", response_model=CourseSchema)
async def update_course(
    course_id: int,
    course_data: CourseCreateSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Update course (only course teacher or admin)"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check permissions
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update course fields
    course.title = course_data.title
    course.description = course_data.description
    course.cover_image_url = course_data.cover_image_url
    course.estimated_duration_minutes = course_data.estimated_duration_minutes
    
    db.commit()
    db.refresh(course)
    
    # Return with teacher info
    teacher = db.query(UserInDB).filter(UserInDB.id == course.teacher_id).first()
    module_count = db.query(Module).filter(Module.course_id == course.id).count()
    
    course_response = CourseSchema.from_orm(course)
    course_response.teacher_name = teacher.name if teacher else "Unknown"
    course_response.total_modules = module_count
    
    return course_response

@router.post("/{course_id}/recalculate-duration")
async def recalculate_course_duration(
    course_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Recalculate and update course duration based on all steps"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check permissions
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Calculate and update duration
    new_duration = update_course_duration(course_id, db)
    
    return {
        "detail": "Course duration recalculated successfully",
        "course_id": course_id,
        "estimated_duration_minutes": new_duration
    }

@router.post("/{course_id}/publish")
async def publish_course(
    course_id: int,
    current_user: UserInDB = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """Publish course from draft to active (admin only)"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check if course is already active
    if course.is_active:
        raise HTTPException(status_code=400, detail="Course is already published")
    
    # Publish the course
    course.is_active = True
    course.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(course)
    
    return {
        "detail": "Course published successfully",
        "course_id": course.id,
        "is_active": course.is_active,
        "status": "active"
    }

@router.post("/{course_id}/unpublish")
async def unpublish_course(
    course_id: int,
    current_user: UserInDB = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """Unpublish course from active to draft (admin only)"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check if course is already in draft
    if not course.is_active:
        raise HTTPException(status_code=400, detail="Course is already in draft")
    
    # Unpublish the course
    course.is_active = False
    course.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(course)
    
    return {
        "detail": "Course unpublished successfully",
        "course_id": course.id,
        "is_active": course.is_active,
        "status": "draft"
    }

@router.delete("/{course_id}")
async def delete_course(
    course_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Delete course (only course teacher or admin)"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check permissions
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Soft delete - mark as inactive
    course.is_active = False
    db.commit()
    
    return {"detail": "Course deleted successfully"}

# =============================================================================
# MODULE MANAGEMENT
# =============================================================================

@router.get("/{course_id}/modules", response_model=List[ModuleSchema])
async def get_course_modules(
    course_id: int,
    include_lessons: bool = Query(False, description="Include lessons for each module"),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get all modules for a course"""
    # Check course access
    if not check_course_access(course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this course")
    
    # Get modules with lesson counts in a single query using subquery
    from sqlalchemy import func
    
    lesson_counts = db.query(
        Lesson.module_id,
        func.count(Lesson.id).label('lesson_count')
    ).filter(
        Lesson.module_id.in_(
            db.query(Module.id).filter(Module.course_id == course_id)
        )
    ).group_by(Lesson.module_id).all()
    
    # Create a map of module_id to lesson_count
    lesson_count_map = {module_id: count for module_id, count in lesson_counts}
    
    # Fetch progress if user is a student
    completed_step_ids = set()
    completed_lesson_ids = set()
    
    if current_user.role == "student":
        # Get completed steps
        from src.schemas.models import StepProgress
        completed_steps = db.query(StepProgress.step_id).filter(
            StepProgress.user_id == current_user.id,
            StepProgress.course_id == course_id,
            StepProgress.status == "completed"
        ).all()
        completed_step_ids = {s[0] for s in completed_steps}
        
        # Get completed lessons (from StudentProgress)
        completed_lessons = db.query(StudentProgress.lesson_id).filter(
            StudentProgress.user_id == current_user.id,
            StudentProgress.course_id == course_id,
            StudentProgress.status == "completed",
            StudentProgress.lesson_id.isnot(None)
        ).all()
        completed_lesson_ids = {l[0] for l in completed_lessons}
    
    # Use joinedload to control lesson loading
    
    if include_lessons:
        modules = db.query(Module).options(
            joinedload(Module.lessons).joinedload(Lesson.steps)
        ).filter(
            Module.course_id == course_id
        ).order_by(Module.order_index).all()
    else:
        modules = db.query(Module).filter(
            Module.course_id == course_id
        ).order_by(Module.order_index).all()
    
    # Enrich with lesson counts
    modules_data = []
    for module in modules:
        # Create module data without lessons first
        module_dict = {
            "id": module.id,
            "course_id": module.course_id,
            "title": module.title,
            "description": module.description,
            "order_index": module.order_index,
            "total_lessons": lesson_count_map.get(module.id, 0),
            "created_at": module.created_at
        }
        
        # Include lessons if requested
        if include_lessons:
            # Use already loaded lessons from joinedload
            lessons = sorted(module.lessons, key=lambda x: x.order_index)
            
            lessons_data = []
            for lesson in lessons:
                # Get steps for this lesson
                steps = sorted(lesson.steps, key=lambda x: x.order_index) if lesson.steps else []
                
                lesson_schema = LessonSchema.from_orm(lesson)
                lesson_schema.steps = []
                
                # Check if all steps are completed to mark lesson as completed
                all_steps_completed = True if steps else False
                
                for step in steps:
                    step_schema = StepSchema.from_orm(step)
                    step_schema.is_completed = step.id in completed_step_ids
                    lesson_schema.steps.append(step_schema)
                    
                    if not step_schema.is_completed:
                        all_steps_completed = False
                
                lesson_schema.total_steps = len(steps)
                
                # Determine lesson completion
                if lesson.id in completed_lesson_ids:
                    lesson_schema.is_completed = True
                elif steps and all_steps_completed:
                    lesson_schema.is_completed = True
                else:
                    lesson_schema.is_completed = False
                
                lessons_data.append(lesson_schema.model_dump())
            
            # Add lessons to module data
            module_dict["lessons"] = lessons_data
            
            # Check if all lessons in module are completed
            if lessons_data and all(l["is_completed"] for l in lessons_data):
                module_dict["is_completed"] = True
            else:
                module_dict["is_completed"] = False
        
        modules_data.append(module_dict)
    
    return modules_data

@router.post("/{course_id}/modules", response_model=ModuleSchema)
async def create_module(
    course_id: int,
    module_data: ModuleCreateSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Create new module in course"""
    # Check course exists and permissions
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    new_module = Module(
        course_id=course_id,
        title=module_data.title,
        description=module_data.description,
        order_index=module_data.order_index
    )
    
    db.add(new_module)
    db.commit()
    db.refresh(new_module)
    
    module_response = ModuleSchema.from_orm(new_module)
    module_response.total_lessons = 0
    
    return module_response

@router.put("/{course_id}/modules/{module_id}", response_model=ModuleSchema)
async def update_module(
    course_id: int,
    module_id: int,
    module_data: ModuleCreateSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Update module"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    module = db.query(Module).filter(
        Module.id == module_id,
        Module.course_id == course_id
    ).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    
    # Check permissions
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    module.title = module_data.title
    module.description = module_data.description
    module.order_index = module_data.order_index
    
    db.commit()
    db.refresh(module)
    
    lesson_count = db.query(Lesson).filter(Lesson.module_id == module.id).count()
    module_response = ModuleSchema.from_orm(module)
    module_response.total_lessons = lesson_count
    
    return module_response

@router.delete("/{course_id}/modules/{module_id}")
async def delete_module(
    course_id: int,
    module_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Delete module and all its lessons"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    module = db.query(Module).filter(
        Module.id == module_id,
        Module.course_id == course_id
    ).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    
    # Check permissions
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    db.delete(module)
    db.commit()
    
    return {"detail": "Module deleted successfully"}

# =============================================================================
# LESSON MANAGEMENT
# =============================================================================

@router.get("/{course_id}/modules/{module_id}/lessons", response_model=List[LessonSchema])
async def get_module_lessons(
    course_id: int,
    module_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get all lessons for a module"""
    # Check course access
    if not check_course_access(course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this course")
    
    # Get lessons with steps
    
    lessons = db.query(Lesson).options(
        joinedload(Lesson.steps)
    ).filter(
        Lesson.module_id == module_id
    ).order_by(Lesson.order_index).all()
    
    lessons_data = []
    for lesson in lessons:
        # Get steps for this lesson
        steps = sorted(lesson.steps, key=lambda x: x.order_index) if lesson.steps else []
        
        lesson_schema = LessonSchema.from_orm(lesson)
        lesson_schema.steps = [StepSchema.from_orm(step) for step in steps]
        lesson_schema.total_steps = len(steps)
        
        lessons_data.append(lesson_schema)
    
    return lessons_data

@router.get("/{course_id}/lessons", response_model=List[LessonSchema])
async def get_course_lessons(
    course_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get all lessons for a course with module information"""
    # Check course access
    if not check_course_access(course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this course")
    
    # Get all lessons for the course with module information and steps
    
    lessons = db.query(Lesson).join(Module).options(
        joinedload(Lesson.steps)
    ).filter(
        Module.course_id == course_id
    ).order_by(Module.order_index, Lesson.order_index).all()
    
    lessons_data = []
    for lesson in lessons:
        # Get steps for this lesson
        steps = sorted(lesson.steps, key=lambda x: x.order_index) if lesson.steps else []
        
        lesson_schema = LessonSchema.from_orm(lesson)
        lesson_schema.steps = [StepSchema.from_orm(step) for step in steps]
        lesson_schema.total_steps = len(steps)
        
        lessons_data.append(lesson_schema)
    
    return lessons_data



@router.post("/{course_id}/modules/{module_id}/lessons", response_model=LessonSchema)
async def create_lesson(
    course_id: int,
    module_id: int,
    lesson_data: LessonCreateSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Create new lesson in module"""
    # Check course and module exist
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    module = db.query(Module).filter(
        Module.id == module_id,
        Module.course_id == course_id
    ).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    
    # Check permissions
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Calculate order_index if not provided or if it's 0
    if lesson_data.order_index == 0:
        # Get the highest order_index in this module and add 1
        max_order = db.query(func.max(Lesson.order_index)).filter(
            Lesson.module_id == module_id
        ).scalar() or 0
        calculated_order_index = max_order + 1
    else:
        calculated_order_index = lesson_data.order_index
    
    new_lesson = Lesson(
        module_id=module_id,
        title=lesson_data.title,
        description=lesson_data.description,
        duration_minutes=lesson_data.duration_minutes,
        order_index=calculated_order_index,
        next_lesson_id=lesson_data.next_lesson_id
    )
    
    db.add(new_lesson)
    db.commit()
    db.refresh(new_lesson)
    
    lesson_schema = LessonSchema.from_orm(new_lesson)
    lesson_schema.steps = []
    lesson_schema.total_steps = 0
    
    return lesson_schema

@router.get("/lessons/{lesson_id}", response_model=LessonSchema)
async def get_lesson(
    lesson_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get lesson details with course access check"""
    
    lesson = db.query(Lesson).options(
        joinedload(Lesson.steps)
    ).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    # Get course_id through module
    module = db.query(Module).filter(Module.id == lesson.module_id).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    
    # Check course access
    if not check_course_access(module.course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this lesson")
    
    # Get steps for this lesson
    steps = sorted(lesson.steps, key=lambda x: x.order_index) if lesson.steps else []
    
    lesson_schema = LessonSchema.from_orm(lesson)
    lesson_schema.steps = [StepSchema.from_orm(step) for step in steps]
    lesson_schema.total_steps = len(steps)
    
    return lesson_schema



@router.put("/lessons/{lesson_id}", response_model=LessonSchema)
async def update_lesson(
    lesson_id: int,
    lesson_data: LessonCreateSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Update lesson"""
    
    lesson = db.query(Lesson).options(
        joinedload(Lesson.steps)
    ).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    # Get course through module and check permissions
    module = db.query(Module).filter(Module.id == lesson.module_id).first()
    course = db.query(Course).filter(Course.id == module.course_id).first()
    
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update lesson fields
    lesson.title = lesson_data.title
    lesson.description = lesson_data.description
    lesson.duration_minutes = lesson_data.duration_minutes
    # Update explicit next lesson if provided (can be None)
    lesson.next_lesson_id = lesson_data.next_lesson_id
    
    # Only update order_index if it's not 0 (preserve existing order)
    if lesson_data.order_index != 0:
        lesson.order_index = lesson_data.order_index
    
    db.commit()
    db.refresh(lesson)
    
    # Get steps for this lesson
    steps = sorted(lesson.steps, key=lambda x: x.order_index) if lesson.steps else []
    
    lesson_schema = LessonSchema.from_orm(lesson)
    lesson_schema.steps = [StepSchema.from_orm(step) for step in steps]
    lesson_schema.total_steps = len(steps)
    
    return lesson_schema

@router.delete("/lessons/{lesson_id}")
async def delete_lesson(
    lesson_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Delete lesson"""
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    # Get course through module and check permissions
    module = db.query(Module).filter(Module.id == lesson.module_id).first()
    course = db.query(Course).filter(Course.id == module.course_id).first()
    
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    db.delete(lesson)
    db.commit()
    
    return {"detail": "Lesson deleted successfully"}

# =============================================================================
# STEP MANAGEMENT
# =============================================================================

@router.get("/lessons/{lesson_id}/steps", response_model=List[StepSchema])
async def get_lesson_steps(
    lesson_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get all steps for a lesson"""
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    # Get course through module and check access
    module = db.query(Module).filter(Module.id == lesson.module_id).first()
    if not check_course_access(module.course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this lesson")
    
    steps = db.query(Step).filter(
        Step.lesson_id == lesson_id
    ).order_by(Step.order_index).all()
    
    return [StepSchema.from_orm(step) for step in steps]

@router.post("/lessons/{lesson_id}/steps", response_model=StepSchema)
async def create_step(
    lesson_id: int,
    step_data: StepCreateSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Create new step in lesson"""
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    # Get course through module and check permissions
    module = db.query(Module).filter(Module.id == lesson.module_id).first()
    course = db.query(Course).filter(Course.id == module.course_id).first()
    
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Calculate order_index if not provided or if it's 0
    if step_data.order_index == 0:
        # Get the highest order_index in this lesson and add 1
        max_order = db.query(func.max(Step.order_index)).filter(
            Step.lesson_id == lesson_id
        ).scalar() or 0
        calculated_order_index = max_order + 1
    else:
        calculated_order_index = step_data.order_index
    
    # Handle quiz data for quiz content type
    content_text = step_data.content_text
    if step_data.content_type == "quiz" and step_data.content_text:
        # For quiz type, content_text should contain quiz data JSON
        # This will be handled by the frontend
        pass
    
    new_step = Step(
        lesson_id=lesson_id,
        title=step_data.title,
        content_type=step_data.content_type,
        video_url=step_data.video_url,
        content_text=content_text,
        original_image_url=step_data.original_image_url,
        attachments=step_data.attachments,
        order_index=calculated_order_index
    )
    
    db.add(new_step)
    db.commit()
    db.refresh(new_step)
    
    # Update course duration
    update_course_duration(course.id, db)
    
    return StepSchema.from_orm(new_step)

@router.get("/steps/{step_id}", response_model=StepSchema)
async def get_step(
    step_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get step details"""
    step = db.query(Step).filter(Step.id == step_id).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    
    # Get course through lesson and module, check access
    lesson = db.query(Lesson).filter(Lesson.id == step.lesson_id).first()
    module = db.query(Module).filter(Module.id == lesson.module_id).first()
    
    if not check_course_access(module.course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied to this step")
    
    return StepSchema.from_orm(step)

@router.put("/steps/{step_id}", response_model=StepSchema)
async def update_step(
    step_id: int,
    step_data: StepCreateSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Update step"""
    step = db.query(Step).filter(Step.id == step_id).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    
    # Get course through lesson and module, check permissions
    lesson = db.query(Lesson).filter(Lesson.id == step.lesson_id).first()
    module = db.query(Module).filter(Module.id == lesson.module_id).first()
    course = db.query(Course).filter(Course.id == module.course_id).first()
    
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Handle quiz data for quiz content type
    content_text = step_data.content_text
    if step_data.content_type == "quiz" and step_data.content_text:
        # For quiz type, content_text should contain quiz data JSON
        pass
    
    # Update step fields
    step.title = step_data.title
    step.content_type = step_data.content_type
    step.video_url = step_data.video_url
    step.content_text = content_text
    step.original_image_url = step_data.original_image_url
    
    # Update attachments if provided
    if step_data.attachments is not None:
        step.attachments = step_data.attachments
    
    # Only update order_index if it's not 0 (preserve existing order)
    if step_data.order_index != 0:
        step.order_index = step_data.order_index
    
    db.commit()
    db.refresh(step)
    
    # Update course duration
    update_course_duration(course.id, db)
    
    return StepSchema.from_orm(step)

@router.post("/lessons/{lesson_id}/reorder-steps")
async def reorder_steps(
    lesson_id: int,
    step_orders: dict,  # Expected format: {"step_ids": [1, 3, 2, 4]}
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Reorder steps in a lesson by updating their order_index"""
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    # Get course through module, check permissions
    module = db.query(Module).filter(Module.id == lesson.module_id).first()
    course = db.query(Course).filter(Course.id == module.course_id).first()
    
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get the new order of step IDs
    step_ids = step_orders.get("step_ids", [])
    if not step_ids:
        raise HTTPException(status_code=400, detail="step_ids is required")
    
    # Verify all steps belong to this lesson
    steps = db.query(Step).filter(Step.lesson_id == lesson_id).all()
    step_id_set = {step.id for step in steps}
    
    for step_id in step_ids:
        if step_id not in step_id_set:
            raise HTTPException(status_code=400, detail=f"Step {step_id} does not belong to lesson {lesson_id}")
    
    # Update order_index for each step
    for new_index, step_id in enumerate(step_ids, start=1):
        step = db.query(Step).filter(Step.id == step_id).first()
        if step:
            step.order_index = new_index
    
    db.commit()
    
    return {"message": "Steps reordered successfully", "step_ids": step_ids}

@router.delete("/steps/{step_id}")
async def delete_step(
    step_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Delete step"""
    step = db.query(Step).filter(Step.id == step_id).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    
    # Get course through lesson and module, check permissions
    lesson = db.query(Lesson).filter(Lesson.id == step.lesson_id).first()
    module = db.query(Module).filter(Module.id == lesson.module_id).first()
    course = db.query(Course).filter(Course.id == module.course_id).first()
    
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Delete related step progress records first
    from src.schemas.models import StepProgress
    step_progress_records = db.query(StepProgress).filter(StepProgress.step_id == step_id).all()
    for record in step_progress_records:
        db.delete(record)
    
    # Now delete the step
    db.delete(step)
    db.commit()
    
    # Update course duration
    update_course_duration(course.id, db)
    
    return {"detail": "Step deleted successfully"}

@router.post("/{course_id}/fix-lesson-order")
async def fix_lesson_order(
    course_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Fix lesson order for a course by reassigning order_index values"""
    # Check course access
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all modules for the course
    modules = db.query(Module).filter(Module.course_id == course_id).order_by(Module.order_index).all()
    
    fixed_count = 0
    for module in modules:
        # Get all lessons for this module
        lessons = db.query(Lesson).filter(Lesson.module_id == module.id).order_by(Lesson.id).all()
        
        # Reassign order_index values
        for index, lesson in enumerate(lessons):
            if lesson.order_index == 0 or lesson.order_index != index + 1:
                lesson.order_index = index + 1
                fixed_count += 1
    
    if fixed_count > 0:
        db.commit()
    
    return {"message": f"Fixed order for {fixed_count} lessons", "fixed_count": fixed_count}

# =============================================================================
# LESSON MATERIALS
# =============================================================================

@router.get("/lessons/{lesson_id}/materials", response_model=List[LessonMaterialSchema])
async def get_lesson_materials(
    lesson_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get all materials for a lesson"""
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    # Check access through course
    module = db.query(Module).filter(Module.id == lesson.module_id).first()
    if not check_course_access(module.course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")
    
    materials = db.query(LessonMaterial).filter(
        LessonMaterial.lesson_id == lesson_id
    ).all()
    
    return [LessonMaterialSchema.from_orm(material) for material in materials]

# =============================================================================
# COURSE ENROLLMENT
# =============================================================================

@router.post("/{course_id}/enroll")
async def enroll_student(
    course_id: int,
    student_id: Optional[int] = None,  # For admin/teacher to enroll specific student
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Enroll student in course"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Determine who to enroll
    target_user_id = student_id if student_id and current_user.role in ["admin", "teacher"] else current_user.id
    
    # Check if already enrolled
    existing_enrollment = db.query(Enrollment).filter(
        Enrollment.user_id == target_user_id,
        Enrollment.course_id == course_id
    ).first()
    
    if existing_enrollment:
        if existing_enrollment.is_active:
            raise HTTPException(status_code=400, detail="Already enrolled in this course")
        else:
            # Reactivate enrollment
            existing_enrollment.is_active = True
            db.commit()
            return {"detail": "Enrollment reactivated"}
    
    # Create new enrollment
    enrollment = Enrollment(
        user_id=target_user_id,
        course_id=course_id,
        is_active=True
    )
    
    db.add(enrollment)
    db.commit()
    
    return {"detail": "Successfully enrolled in course"}

@router.post("/{course_id}/auto-enroll-students")
async def auto_enroll_students(
    course_id: int,
    current_user: UserInDB = Depends(require_teacher_or_admin()),
    db: Session = Depends(get_db)
):
    """Automatically enroll all students in teacher's groups to the course"""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check if user is the course teacher or admin
    if current_user.role != "admin" and course.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all students in teacher's groups
    from src.schemas.models import GroupStudent
    
    if current_user.role == "teacher":
        # Get all groups created by this teacher
        teacher_groups = db.query(Group).filter(Group.teacher_id == current_user.id).all()
        group_ids = [group.id for group in teacher_groups]
    else:
        # Admin can enroll all students
        group_ids = db.query(Group.id).all()
        group_ids = [g[0] for g in group_ids]
    
    if not group_ids:
        return {"detail": "No groups found for auto-enrollment"}
    
    # Get all students in these groups
    group_students = db.query(GroupStudent).filter(
        GroupStudent.group_id.in_(group_ids)
    ).all()
    
    enrolled_count = 0
    already_enrolled_count = 0
    
    for group_student in group_students:
        # Check if already enrolled
        existing_enrollment = db.query(Enrollment).filter(
            Enrollment.user_id == group_student.student_id,
            Enrollment.course_id == course_id
        ).first()
        
        if existing_enrollment:
            if not existing_enrollment.is_active:
                # Reactivate enrollment
                existing_enrollment.is_active = True
                enrolled_count += 1
            else:
                already_enrolled_count += 1
        else:
            # Create new enrollment
            enrollment = Enrollment(
                user_id=group_student.student_id,
                course_id=course_id,
                is_active=True
            )
            db.add(enrollment)
            enrolled_count += 1
    
    db.commit()
    
    return {
        "detail": f"Auto-enrollment completed",
        "enrolled_count": enrolled_count,
        "already_enrolled_count": already_enrolled_count,
        "total_students": len(group_students)
    }

@router.delete("/{course_id}/enroll")
async def unenroll_student(
    course_id: int,
    student_id: Optional[int] = None,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Remove student from course"""
    target_user_id = student_id if student_id and current_user.role in ["admin", "teacher"] else current_user.id
    
    enrollment = db.query(Enrollment).filter(
        Enrollment.user_id == target_user_id,
        Enrollment.course_id == course_id,
        Enrollment.is_active == True
    ).first()
    
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    
    # Soft delete enrollment
    enrollment.is_active = False
    db.commit()
    
    return {"detail": "Successfully unenrolled from course"}

# =============================================================================
# COURSE GROUP ACCESS MANAGEMENT
# =============================================================================

@router.get("/{course_id}/groups", response_model=List[CourseGroupAccessSchema])
async def get_course_groups(
    course_id: int,
    current_user: UserInDB = Depends(require_teacher_or_admin()),
    db: Session = Depends(get_db)
):
    """Get groups that have access to a course"""
    # Check if course exists and user has access
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    if not check_course_access(course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get group access records
    group_access = db.query(CourseGroupAccess).filter(
        CourseGroupAccess.course_id == course_id,
        CourseGroupAccess.is_active == True
    ).all()
    
    # Enrich with group and user information
    result = []
    for access in group_access:
        group = db.query(Group).filter(Group.id == access.group_id).first()
        granted_by_user = db.query(UserInDB).filter(UserInDB.id == access.granted_by).first()
        
        # Count students in group using GroupStudent association table
        student_count = db.query(GroupStudent).filter(
            GroupStudent.group_id == access.group_id
        ).count()
        
        access_data = CourseGroupAccessSchema.from_orm(access)
        access_data.group_name = group.name if group else "Unknown Group"
        access_data.student_count = student_count
        access_data.granted_by_name = granted_by_user.name if granted_by_user else "Unknown"
        
        result.append(access_data)
    
    return result

@router.post("/{course_id}/grant-group-access/{group_id}")
async def grant_course_access_to_group(
    course_id: int,
    group_id: int,
    current_user: UserInDB = Depends(require_teacher_or_admin()),
    db: Session = Depends(get_db)
):
    """Grant access to a course for a specific group"""
    # Check if course exists and user has access
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    if not check_course_access(course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if group exists
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Check if access already exists
    existing_access = db.query(CourseGroupAccess).filter(
        CourseGroupAccess.course_id == course_id,
        CourseGroupAccess.group_id == group_id,
        CourseGroupAccess.is_active == True
    ).first()
    
    if existing_access:
        return {
            "detail": f"Group '{group.name}' already has access to this course",
            "status": "already_granted",
            "access_id": existing_access.id
        }
    
    # Create new access record
    access = CourseGroupAccess(
        course_id=course_id,
        group_id=group_id,
        granted_by=current_user.id,
        is_active=True
    )
    
    db.add(access)
    db.commit()
    
    return {
        "detail": f"Access granted to group '{group.name}'",
        "status": "granted",
        "access_id": access.id
    }

@router.delete("/{course_id}/revoke-group-access/{group_id}")
async def revoke_course_access_from_group(
    course_id: int,
    group_id: int,
    current_user: UserInDB = Depends(require_teacher_or_admin()),
    db: Session = Depends(get_db)
):
    """Revoke access to a course for a specific group"""
    # Check if course exists and user has access
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    if not check_course_access(course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Find and deactivate access record
    access = db.query(CourseGroupAccess).filter(
        CourseGroupAccess.course_id == course_id,
        CourseGroupAccess.group_id == group_id,
        CourseGroupAccess.is_active == True
    ).first()
    
    if not access:
        raise HTTPException(status_code=404, detail="Group access not found")
    
    # Get group name for response
    group = db.query(Group).filter(Group.id == group_id).first()
    group_name = group.name if group else "Unknown Group"
    
    # Soft delete access
    access.is_active = False
    db.commit()
    
    return {"detail": f"Access revoked from group '{group_name}'"}

@router.get("/{course_id}/group-access-status")
async def get_course_group_access_status(
    course_id: int,
    current_user: UserInDB = Depends(require_teacher_or_admin()),
    db: Session = Depends(get_db)
):
    """Get status of group access for a course"""
    # Check if course exists and user has access
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    if not check_course_access(course_id, current_user, db):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all groups that have access to this course
    group_access = db.query(CourseGroupAccess).filter(
        CourseGroupAccess.course_id == course_id,
        CourseGroupAccess.is_active == True
    ).all()
    
    # Get group IDs that have access
    group_ids_with_access = [access.group_id for access in group_access]
    
    return {
        "course_id": course_id,
        "groups_with_access": group_ids_with_access,
        "total_groups_with_access": len(group_ids_with_access)
    }

@router.post("/analyze-sat-image")
async def analyze_sat_image(
    image: UploadFile = File(...),
    current_user: UserInDB = Depends(require_teacher_or_admin()),
    db: Session = Depends(get_db)
):
    """
    Analyze SAT question image using Azure OpenAI Vision API
    Upload an image of a SAT question and get structured question data
    """
    try:
        # Validate file type
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Create uploads directory if it doesn't exist
        uploads_dir = "uploads/sat_images"
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Generate unique filename
        file_extension = os.path.splitext(image.filename)[1] if image.filename else '.png'
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(uploads_dir, unique_filename)
        
        # Save uploaded file
        content = await image.read()
        async with aiofiles.open(file_path, "wb") as buffer:
            await buffer.write(content)
        
        # Initialize Azure OpenAI service
        azure_service = AzureOpenAIService()
        
        # Analyze the image
        result = await azure_service.analyze_sat_image(file_path)
        
        # Add file path to result for reference
        result["image_url"] = f"/uploads/sat_images/{unique_filename}"
        result["original_filename"] = image.filename
        
        # Clean up the temporary file
        try:
            os.remove(file_path)
        except:
            pass  # Don't fail if cleanup fails
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing image: {str(e)}")
