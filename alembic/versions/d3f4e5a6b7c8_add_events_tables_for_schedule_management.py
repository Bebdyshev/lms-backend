"""add_events_tables_for_schedule_management

Revision ID: d3f4e5a6b7c8
Revises: 3cae8f299731
Create Date: 2025-09-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3f4e5a6b7c8'
down_revision: Union[str, Sequence[str], None] = '3cae8f299731'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create events table
    op.create_table('events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('start_datetime', sa.DateTime(), nullable=False),
        sa.Column('end_datetime', sa.DateTime(), nullable=False),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('is_online', sa.Boolean(), nullable=True, default=True),
        sa.Column('meeting_url', sa.String(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('is_recurring', sa.Boolean(), nullable=True, default=False),
        sa.Column('recurrence_pattern', sa.String(), nullable=True),
        sa.Column('recurrence_end_date', sa.Date(), nullable=True),
        sa.Column('max_participants', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_events_id'), 'events', ['id'], unique=False)

    # Create event_groups table
    op.create_table('event_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'group_id', name='uq_event_group')
    )
    op.create_index(op.f('ix_event_groups_id'), 'event_groups', ['id'], unique=False)

    # Create event_participants table
    op.create_table('event_participants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('registration_status', sa.String(), nullable=True, default='registered'),
        sa.Column('registered_at', sa.DateTime(), nullable=True),
        sa.Column('attended_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'user_id', name='uq_event_participant')
    )
    op.create_index(op.f('ix_event_participants_id'), 'event_participants', ['id'], unique=False)

    # Add indexes for better performance
    op.create_index('ix_events_start_datetime', 'events', ['start_datetime'])
    op.create_index('ix_events_event_type', 'events', ['event_type'])
    op.create_index('ix_events_created_by', 'events', ['created_by'])
    op.create_index('ix_event_groups_event_id', 'event_groups', ['event_id'])
    op.create_index('ix_event_groups_group_id', 'event_groups', ['group_id'])
    op.create_index('ix_event_participants_event_id', 'event_participants', ['event_id'])
    op.create_index('ix_event_participants_user_id', 'event_participants', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('ix_event_participants_user_id', table_name='event_participants')
    op.drop_index('ix_event_participants_event_id', table_name='event_participants')
    op.drop_index('ix_event_groups_group_id', table_name='event_groups')
    op.drop_index('ix_event_groups_event_id', table_name='event_groups')
    op.drop_index('ix_events_created_by', table_name='events')
    op.drop_index('ix_events_event_type', table_name='events')
    op.drop_index('ix_events_start_datetime', table_name='events')
    
    # Drop tables
    op.drop_index(op.f('ix_event_participants_id'), table_name='event_participants')
    op.drop_table('event_participants')
    op.drop_index(op.f('ix_event_groups_id'), table_name='event_groups')
    op.drop_table('event_groups')
    op.drop_index(op.f('ix_events_id'), table_name='events')
    op.drop_table('events')
