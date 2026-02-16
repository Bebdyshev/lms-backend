"""add confirmed_teacher_id column

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-02-15 22:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('lesson_requests', sa.Column('confirmed_teacher_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_lesson_requests_confirmed_teacher_id',
        'lesson_requests',
        'users',
        ['confirmed_teacher_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_lesson_requests_confirmed_teacher_id', 'lesson_requests', type_='foreignkey')
    op.drop_column('lesson_requests', 'confirmed_teacher_id')
