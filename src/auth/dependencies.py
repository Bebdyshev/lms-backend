# Auth dependencies: re-exports from original locations.
# Core auth functions and route-level dependencies live here for domain cohesion.
# Old import paths (src.utils.auth_utils, src.utils.permissions) still work.

from src.utils.auth_utils import (  # noqa: F401
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_MINUTES,
)

from src.utils.permissions import (  # noqa: F401
    require_role,
    require_admin,
    require_teacher_or_admin,
    require_teacher_or_admin_for_groups,
    require_curator_or_admin,
    require_teacher_curator_or_admin,
    check_course_access,
    require_course_access,
    check_student_access,
    require_student_access,
    check_group_access,
    require_group_access,
    can_create_course,
    can_edit_course,
    can_create_assignment,
    can_grade_assignment,
    has_higher_or_equal_role,
    ROLE_HIERARCHY,
)
