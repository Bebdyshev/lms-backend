"""add event_id to attendances and make lesson_schedule_id nullable

Revision ID: a1b2c3d4e5f7
Revises: 2518438537dd
Create Date: 2026-02-25 00:00:00.000000

Single source of truth for attendance: Attendance table covers both
Event-based lessons (event_id) and legacy LessonSchedule-based (lesson_schedule_id).
Exactly one of the two must be set (enforced by CHECK constraint).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, Sequence[str], None] = '2518438537dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add event_id column (nullable FK → events)
    op.add_column(
        'attendances',
        sa.Column('event_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_attendances_event_id',
        'attendances', 'events',
        ['event_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_attendances_event_id', 'attendances', ['event_id'])

    # 2. Make lesson_schedule_id nullable (existing rows keep their value)
    op.alter_column(
        'attendances', 'lesson_schedule_id',
        existing_type=sa.Integer(),
        nullable=True
    )

    # 3. Drop the old CASCADE FK and recreate with nullable support
    op.drop_constraint('attendances_lesson_schedule_id_fkey', 'attendances', type_='foreignkey')
    op.create_foreign_key(
        'fk_attendances_lesson_schedule_id',
        'attendances', 'lesson_schedules',
        ['lesson_schedule_id'], ['id'],
        ondelete='CASCADE'
    )

    # 4. CHECK: exactly one of event_id / lesson_schedule_id must be set
    op.create_check_constraint(
        'ck_attendance_event_or_schedule',
        'attendances',
        '(event_id IS NOT NULL AND lesson_schedule_id IS NULL) OR '
        '(event_id IS NULL AND lesson_schedule_id IS NOT NULL)'
    )

    # 5. Unique constraint: one Attendance per (event_id, user_id)
    op.create_unique_constraint(
        'uq_attendance_event_user',
        'attendances',
        ['event_id', 'user_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_attendance_event_user', 'attendances', type_='unique')
    op.drop_constraint('ck_attendance_event_or_schedule', 'attendances', type_='check')
    op.drop_constraint('fk_attendances_lesson_schedule_id', 'attendances', type_='foreignkey')
    op.create_foreign_key(
        'attendances_lesson_schedule_id_fkey',
        'attendances', 'lesson_schedules',
        ['lesson_schedule_id'], ['id'],
        ondelete='CASCADE'
    )
    op.alter_column(
        'attendances', 'lesson_schedule_id',
        existing_type=sa.Integer(),
        nullable=False
    )
    op.drop_index('ix_attendances_event_id', table_name='attendances')
    op.drop_constraint('fk_attendances_event_id', 'attendances', type_='foreignkey')
    op.drop_column('attendances', 'event_id')
