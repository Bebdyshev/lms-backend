"""add_activity_score_to_attendance_and_event_participant

Revision ID: i1j2k3l4m5n6
Revises: b8407ede1000
Create Date: 2026-02-04 10:47:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i1j2k3l4m5n6'
down_revision = 'b8407ede1000'
branch_labels = None
depends_on = None


def upgrade():
    # Add activity_score to event_participants
    op.add_column('event_participants', sa.Column('activity_score', sa.Float(), nullable=True))
    
    # Add activity_score to attendances
    op.add_column('attendances', sa.Column('activity_score', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('event_participants', 'activity_score')
    op.drop_column('attendances', 'activity_score')
