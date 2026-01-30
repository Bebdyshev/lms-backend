"""add_course_head_teachers_table

Revision ID: 9fdd87126046
Revises: b6f6481e12e5
Create Date: 2026-01-30 18:19:56.746781

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fdd87126046'
down_revision: Union[str, Sequence[str], None] = 'b6f6481e12e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the course_head_teachers association table."""
    op.create_table(
        'course_head_teachers',
        sa.Column('course_id', sa.Integer(), sa.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('head_teacher_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('course_id', 'head_teacher_id')
    )
    op.create_index('ix_course_head_teachers_head_teacher_id', 'course_head_teachers', ['head_teacher_id'])


def downgrade() -> None:
    """Drop the course_head_teachers table."""
    op.drop_index('ix_course_head_teachers_head_teacher_id', table_name='course_head_teachers')
    op.drop_table('course_head_teachers')

