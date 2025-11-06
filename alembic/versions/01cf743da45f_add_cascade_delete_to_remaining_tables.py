"""add_cascade_delete_to_remaining_tables

Revision ID: 01cf743da45f
Revises: 4b1d8664985c
Create Date: 2025-11-06 08:47:24.876096

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01cf743da45f'
down_revision: Union[str, Sequence[str], None] = '4b1d8664985c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Steps table - add CASCADE to lesson_id
    op.drop_constraint('steps_lesson_id_fkey', 'steps', type_='foreignkey')
    op.create_foreign_key(
        'steps_lesson_id_fkey',
        'steps', 'lessons',
        ['lesson_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Lesson materials table - add CASCADE to lesson_id
    op.drop_constraint('lesson_materials_lesson_id_fkey', 'lesson_materials', type_='foreignkey')
    op.create_foreign_key(
        'lesson_materials_lesson_id_fkey',
        'lesson_materials', 'lessons',
        ['lesson_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Assignments table - add CASCADE to lesson_id and SET NULL to group_id
    op.drop_constraint('assignments_lesson_id_fkey', 'assignments', type_='foreignkey')
    op.create_foreign_key(
        'assignments_lesson_id_fkey',
        'assignments', 'lessons',
        ['lesson_id'], ['id'],
        ondelete='CASCADE'
    )
    
    op.drop_constraint('assignments_group_id_fkey', 'assignments', type_='foreignkey')
    op.create_foreign_key(
        'assignments_group_id_fkey',
        'assignments', 'groups',
        ['group_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Assignment submissions table - add CASCADE to assignment_id
    op.drop_constraint('assignment_submissions_assignment_id_fkey', 'assignment_submissions', type_='foreignkey')
    op.create_foreign_key(
        'assignment_submissions_assignment_id_fkey',
        'assignment_submissions', 'assignments',
        ['assignment_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Revert Steps
    op.drop_constraint('steps_lesson_id_fkey', 'steps', type_='foreignkey')
    op.create_foreign_key(
        'steps_lesson_id_fkey',
        'steps', 'lessons',
        ['lesson_id'], ['id']
    )
    
    # Revert Lesson materials
    op.drop_constraint('lesson_materials_lesson_id_fkey', 'lesson_materials', type_='foreignkey')
    op.create_foreign_key(
        'lesson_materials_lesson_id_fkey',
        'lesson_materials', 'lessons',
        ['lesson_id'], ['id']
    )
    
    # Revert Assignments
    op.drop_constraint('assignments_lesson_id_fkey', 'assignments', type_='foreignkey')
    op.create_foreign_key(
        'assignments_lesson_id_fkey',
        'assignments', 'lessons',
        ['lesson_id'], ['id']
    )
    
    op.drop_constraint('assignments_group_id_fkey', 'assignments', type_='foreignkey')
    op.create_foreign_key(
        'assignments_group_id_fkey',
        'assignments', 'groups',
        ['group_id'], ['id']
    )
    
    # Revert Assignment submissions
    op.drop_constraint('assignment_submissions_assignment_id_fkey', 'assignment_submissions', type_='foreignkey')
    op.create_foreign_key(
        'assignment_submissions_assignment_id_fkey',
        'assignment_submissions', 'assignments',
        ['assignment_id'], ['id']
    )
