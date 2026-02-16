"""add lesson_requests table and no_substitutions to users

Revision ID: a7f8b9c0d1e2
Revises: 52f742168446
Create Date: 2026-02-15 20:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7f8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = '52f742168446'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add no_substitutions to users
    op.add_column('users', sa.Column('no_substitutions', sa.Boolean(), nullable=False, server_default='false'))

    # Create lesson_requests table
    op.create_table(
        'lesson_requests',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('request_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('requester_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('lesson_schedule_id', sa.Integer(), sa.ForeignKey('lesson_schedules.id', ondelete='SET NULL'), nullable=True),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('events.id', ondelete='SET NULL'), nullable=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('original_datetime', sa.DateTime(), nullable=False),
        sa.Column('substitute_teacher_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('new_datetime', sa.DateTime(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('admin_comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index(op.f('ix_lesson_requests_id'), 'lesson_requests', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_lesson_requests_id'), table_name='lesson_requests')
    op.drop_table('lesson_requests')
    op.drop_column('users', 'no_substitutions')
