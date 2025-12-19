"""Add push_token to users

Revision ID: add_push_token
Revises: 
Create Date: 2024-12-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_push_token'
down_revision = 'bcc94a06e19a'  # Set this to your latest migration revision
branch_labels = None
depends_on = None


def upgrade():
    # Add push_token and device_type columns to users table
    op.add_column('users', sa.Column('push_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('device_type', sa.String(), nullable=True))
    op.create_index('ix_users_push_token', 'users', ['push_token'], unique=False)


def downgrade():
    # Remove the columns
    op.drop_index('ix_users_push_token', table_name='users')
    op.drop_column('users', 'device_type')
    op.drop_column('users', 'push_token')
