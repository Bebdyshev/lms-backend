"""Add gamification point_history table and activity_points to users

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h2i3j4k5l6m7'
down_revision = 'g1h2i3j4k5l6'
branch_labels = None
depends_on = None


def upgrade():
    # Add activity_points column to users table
    op.add_column('users', sa.Column('activity_points', sa.BigInteger(), nullable=False, server_default='0'))
    
    # Create point_history table
    op.create_table('point_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_point_history_id'), 'point_history', ['id'], unique=False)
    op.create_index(op.f('ix_point_history_user_id'), 'point_history', ['user_id'], unique=False)
    op.create_index(op.f('ix_point_history_created_at'), 'point_history', ['created_at'], unique=False)
    op.create_index('ix_point_history_user_created', 'point_history', ['user_id', 'created_at'], unique=False)


def downgrade():
    op.drop_index('ix_point_history_user_created', table_name='point_history')
    op.drop_index(op.f('ix_point_history_created_at'), table_name='point_history')
    op.drop_index(op.f('ix_point_history_user_id'), table_name='point_history')
    op.drop_index(op.f('ix_point_history_id'), table_name='point_history')
    op.drop_table('point_history')
    op.drop_column('users', 'activity_points')
