"""
add next_lesson_id to lessons

Revision ID: 7f3c1a2a9b10
Revises: d2c0eb95ab44
Create Date: 2025-09-12
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f3c1a2a9b10'
down_revision = 'b429e2c93464'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('lessons', sa.Column('next_lesson_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_lessons_next_lesson',
        'lessons', 'lessons',
        ['next_lesson_id'], ['id'],
        ondelete=None
    )


def downgrade() -> None:
    op.drop_constraint('fk_lessons_next_lesson', 'lessons', type_='foreignkey')
    op.drop_column('lessons', 'next_lesson_id')


