from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from src.config import get_db
from src.schemas.models import UserInDB, Course, Group, Enrollment
from src.routes.auth import get_current_user_dependency

def require_role(allowed_roles: List[str]):
    """
    Dependency factory to require specific roles
    Usage: @require_role(["admin", "teacher"])
    """
    def role_checker(current_user: UserInDB = Depends(get_current_user_dependency)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=403, 
                detail=f"Access denied. Required roles: {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker

def require_admin():
    """Require admin role"""
    return require_role(["admin"])

def require_teacher_or_admin():
    """Require teacher or admin role"""
    return require_role(["teacher", "admin"])

def require_teacher_or_admin_for_groups():
    """Require teacher or admin role for group operations"""
    def group_access_checker(current_user: UserInDB = Depends(get_current_user_dependency)):
        if current_user.role not in ["teacher", "admin"]:
            raise HTTPException(
                status_code=403, 
                detail="Access denied. Only teachers and admins can manage groups."
            )
        return current_user
    return group_access_checker

def require_curator_or_admin():
    """Require curator or admin role"""
    return require_role(["curator", "admin"])

def require_teacher_curator_or_admin():
    """Require teacher, curator or admin role"""
    return require_role(["teacher", "curator", "admin"])

def check_course_access(course_id: int, user: UserInDB, db: Session) -> bool:
    """
    Check if user has access to a specific course
    - Students: if enrolled OR if their group has access to the course
    - Teachers: only if they created the course
    - Curators: if they have access to students in the course
    - Admins: always
    """
    if user.role == "admin":
        return True
    
    # Get course
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        return False
    
    if user.role == "teacher":
        # Teachers can access only their own courses
        return course.teacher_id == user.id
    
    elif user.role == "student":
        # Students can access if enrolled OR if their group has access
        # First check individual enrollment
        enrollment = db.query(Enrollment).filter(
            Enrollment.user_id == user.id,
            Enrollment.course_id == course_id,
            Enrollment.is_active == True
        ).first()
        if enrollment:
            return True
        
        # Then check group access
        from src.schemas.models import GroupStudent, CourseGroupAccess
        
        # Find student's group
        group_student = db.query(GroupStudent).filter(
            GroupStudent.student_id == user.id
        ).first()
        
        if group_student:
            # Check if the group has access to this course
            group_access = db.query(CourseGroupAccess).filter(
                CourseGroupAccess.group_id == group_student.group_id,
                CourseGroupAccess.course_id == course_id,
                CourseGroupAccess.is_active == True
            ).first()
            
            if group_access:
                return True
        
        return False
    
    elif user.role == "curator":
        # Curators can access courses if they have students from their groups enrolled
        from src.schemas.models import GroupStudent, Group
        
        # Get groups where user is curator
        curator_groups = db.query(Group).filter(Group.curator_id == user.id).all()
        
        if not curator_groups:
            return False
        
        curator_group_ids = [g.id for g in curator_groups]
        
        # Check if any students from curator's groups are enrolled in this course
        student_ids_in_groups = db.query(GroupStudent.student_id).filter(
            GroupStudent.group_id.in_(curator_group_ids)
        ).subquery()
        
        enrolled_students = db.query(Enrollment).filter(
            Enrollment.course_id == course_id,
            Enrollment.user_id.in_(student_ids_in_groups),
            Enrollment.is_active == True
        ).first()
        
        return enrolled_students is not None
    
    return False

def require_course_access(course_id: int):
    """
    Dependency to require access to a specific course
    Usage: require_course_access(course_id)
    """
    def course_access_checker(
        current_user: UserInDB = Depends(get_current_user_dependency),
        db: Session = Depends(get_db)
    ):
        if not check_course_access(course_id, current_user, db):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this course"
            )
        return current_user
    return course_access_checker

def check_student_access(student_id: int, user: UserInDB, db: Session) -> bool:
    """
    Check if user has access to a specific student's data
    - Students: only their own data
    - Teachers: only their students (enrolled in their courses)
    - Curators: only assigned students
    - Admins: all students
    """
    if user.role == "admin":
        return True
    
    if user.role == "student":
        # Students can only access their own data
        return user.id == student_id
    
    student = db.query(UserInDB).filter(UserInDB.id == student_id).first()
    if not student or student.role != "student":
        return False
    
    if user.role == "teacher":
        # Teachers can access students enrolled in their courses
        teacher_courses = db.query(Course).filter(Course.teacher_id == user.id).all()
        teacher_course_ids = [course.id for course in teacher_courses]
        
        student_enrollments = db.query(Enrollment).filter(
            Enrollment.user_id == student_id,
            Enrollment.course_id.in_(teacher_course_ids),
            Enrollment.is_active == True
        ).first()
        
        return student_enrollments is not None
    
    elif user.role == "curator":
        # Curators can access students in their assigned groups
        from src.schemas.models import GroupStudent, Group
        
        # Get groups where user is curator
        curator_groups = db.query(Group).filter(Group.curator_id == user.id).all()
        
        if not curator_groups:
            return False
        
        curator_group_ids = [g.id for g in curator_groups]
        
        # Check if student is in any of curator's groups
        student_in_group = db.query(GroupStudent).filter(
            GroupStudent.student_id == student_id,
            GroupStudent.group_id.in_(curator_group_ids)
        ).first()
        
        return student_in_group is not None
    
    return False

def require_student_access(student_id: int):
    """
    Dependency to require access to a specific student
    Usage: require_student_access(student_id)
    """
    def student_access_checker(
        current_user: UserInDB = Depends(get_current_user_dependency),
        db: Session = Depends(get_db)
    ):
        if not check_student_access(student_id, current_user, db):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this student's data"
            )
        return current_user
    return student_access_checker

def check_group_access(group_id: int, user: UserInDB, db: Session) -> bool:
    """
    Check if user has access to a specific group
    - Teachers: only if they created the group
    - Curators: only their assigned groups
    - Admins: all groups
    """
    if user.role == "admin":
        return True
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        return False
    
    if user.role == "teacher":
        return group.teacher_id == user.id
    
    elif user.role == "curator":
        # Curators can access their assigned groups
        return user.group_id == group_id
    
    return False

def require_group_access(group_id: int):
    """
    Dependency to require access to a specific group
    Usage: require_group_access(group_id)
    """
    def group_access_checker(
        current_user: UserInDB = Depends(get_current_user_dependency),
        db: Session = Depends(get_db)
    ):
        if not check_group_access(group_id, current_user, db):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this group"
            )
        return current_user
    return group_access_checker

def can_create_course(user: UserInDB) -> bool:
    """Check if user can create courses"""
    return user.role in ["teacher", "admin"]

def can_edit_course(course_id: int, user: UserInDB, db: Session) -> bool:
    """Check if user can edit a specific course"""
    if user.role == "admin":
        return True
    
    if user.role == "teacher":
        course = db.query(Course).filter(Course.id == course_id).first()
        return course and course.teacher_id == user.id
    
    return False

def can_create_assignment(user: UserInDB) -> bool:
    """Check if user can create assignments"""
    return user.role in ["teacher", "admin"]

def can_grade_assignment(assignment_id: int, user: UserInDB, db: Session) -> bool:
    """Check if user can grade a specific assignment"""
    if user.role == "admin":
        return True
    
    if user.role == "teacher":
        # Teachers can grade assignments in their courses
        from src.schemas.models import Assignment, Lesson, Module
        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        if not assignment:
            return False
        
        if assignment.lesson_id:
            lesson = db.query(Lesson).filter(Lesson.id == assignment.lesson_id).first()
            if lesson:
                module = db.query(Module).filter(Module.id == lesson.module_id).first()
                if module:
                    course = db.query(Course).filter(Course.id == module.course_id).first()
                    return course and course.teacher_id == user.id
        
        # For standalone assignments, check if teacher has rights
        # TODO: Implement standalone assignment access logic
        return True
    
    return False

# Role hierarchy for permission checking
ROLE_HIERARCHY = {
    "student": 1,
    "curator": 2,
    "teacher": 3,
    "admin": 4
}

def has_higher_or_equal_role(user_role: str, required_role: str) -> bool:
    """Check if user has higher or equal role than required"""
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 0)
