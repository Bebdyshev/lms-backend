"""add_cascade_delete_to_step_progress

Revision ID: 4b1d8664985c
Revises: 0efd38c08ef8
Create Date: 2025-11-06 08:45:45.126744

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b1d8664985c'
down_revision: Union[str, Sequence[str], None] = '0efd38c08ef8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop existing foreign key constraints
    op.drop_constraint('step_progress_step_id_fkey', 'step_progress', type_='foreignkey')
    op.drop_constraint('step_progress_course_id_fkey', 'step_progress', type_='foreignkey')
    op.drop_constraint('step_progress_lesson_id_fkey', 'step_progress', type_='foreignkey')
    
    # Recreate foreign key constraints with CASCADE delete
    op.create_foreign_key(
        'step_progress_step_id_fkey', 
        'step_progress', 'steps',
        ['step_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'step_progress_course_id_fkey',
        'step_progress', 'courses',
        ['course_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'step_progress_lesson_id_fkey',
        'step_progress', 'lessons',
        ['lesson_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop CASCADE foreign key constraints
    op.drop_constraint('step_progress_step_id_fkey', 'step_progress', type_='foreignkey')
    op.drop_constraint('step_progress_course_id_fkey', 'step_progress', type_='foreignkey')
    op.drop_constraint('step_progress_lesson_id_fkey', 'step_progress', type_='foreignkey')
    
    # Recreate foreign key constraints without CASCADE
    op.create_foreign_key(
        'step_progress_step_id_fkey',
        'step_progress', 'steps',
        ['step_id'], ['id']
    )
    op.create_foreign_key(
        'step_progress_course_id_fkey',
        'step_progress', 'courses',
        ['course_id'], ['id']
    )
    op.create_foreign_key(
        'step_progress_lesson_id_fkey',
        'step_progress', 'lessons',
        ['lesson_id'], ['id']
    )
