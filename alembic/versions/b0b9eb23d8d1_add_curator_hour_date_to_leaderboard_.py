"""add curator_hour_date to leaderboard_configs

Revision ID: b0b9eb23d8d1
Revises: 8ae6a13ab953
Create Date: 2026-01-27 11:04:16.301920

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0b9eb23d8d1'
down_revision: Union[str, Sequence[str], None] = '8ae6a13ab953'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Check if column already exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('leaderboard_configs')]
    if 'curator_hour_date' not in columns:
        op.add_column('leaderboard_configs', sa.Column('curator_hour_date', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('leaderboard_configs', 'curator_hour_date')
