"""add_cascade_delete_to_quiz_attempts

Revision ID: 0efd38c08ef8
Revises: a1b2c3d4e5f6
Create Date: 2025-11-06 08:39:01.668196

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0efd38c08ef8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop existing foreign key constraints
    op.drop_constraint('quiz_attempts_step_id_fkey', 'quiz_attempts', type_='foreignkey')
    op.drop_constraint('quiz_attempts_course_id_fkey', 'quiz_attempts', type_='foreignkey')
    op.drop_constraint('quiz_attempts_lesson_id_fkey', 'quiz_attempts', type_='foreignkey')
    
    # Recreate foreign key constraints with CASCADE delete
    op.create_foreign_key(
        'quiz_attempts_step_id_fkey', 
        'quiz_attempts', 'steps',
        ['step_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'quiz_attempts_course_id_fkey',
        'quiz_attempts', 'courses',
        ['course_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'quiz_attempts_lesson_id_fkey',
        'quiz_attempts', 'lessons',
        ['lesson_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop CASCADE foreign key constraints
    op.drop_constraint('quiz_attempts_step_id_fkey', 'quiz_attempts', type_='foreignkey')
    op.drop_constraint('quiz_attempts_course_id_fkey', 'quiz_attempts', type_='foreignkey')
    op.drop_constraint('quiz_attempts_lesson_id_fkey', 'quiz_attempts', type_='foreignkey')
    
    # Recreate foreign key constraints without CASCADE
    op.create_foreign_key(
        'quiz_attempts_step_id_fkey',
        'quiz_attempts', 'steps',
        ['step_id'], ['id']
    )
    op.create_foreign_key(
        'quiz_attempts_course_id_fkey',
        'quiz_attempts', 'courses',
        ['course_id'], ['id']
    )
    op.create_foreign_key(
        'quiz_attempts_lesson_id_fkey',
        'quiz_attempts', 'lessons',
        ['lesson_id'], ['id']
    )
