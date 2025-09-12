"""add_daily_streak_fields_to_users

Revision ID: 3cae8f299731
Revises: 8a4b2c1d3e5f
Create Date: 2025-09-12 18:10:56.827848

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3cae8f299731'
down_revision: Union[str, Sequence[str], None] = '8a4b2c1d3e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add daily_streak and last_activity_date columns to users table
    op.add_column('users', sa.Column('daily_streak', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('last_activity_date', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove daily_streak and last_activity_date columns from users table
    op.drop_column('users', 'last_activity_date')
    op.drop_column('users', 'daily_streak')
