"""add_onboarding_tracking_to_users

Revision ID: 57e19d19aae8
Revises: 86146539fee2
Create Date: 2025-10-27 12:13:26.502342

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57e19d19aae8'
down_revision: Union[str, Sequence[str], None] = '86146539fee2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add onboarding_completed column
    op.add_column('users', sa.Column('onboarding_completed', sa.Boolean(), nullable=False, server_default='false'))
    # Add onboarding_completed_at column
    op.add_column('users', sa.Column('onboarding_completed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove onboarding columns
    op.drop_column('users', 'onboarding_completed_at')
    op.drop_column('users', 'onboarding_completed')
