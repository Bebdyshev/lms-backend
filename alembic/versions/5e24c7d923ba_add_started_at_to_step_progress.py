"""add_started_at_to_step_progress

Revision ID: 5e24c7d923ba
Revises: d3f4e5a6b7c8
Create Date: 2025-10-07 20:34:35.946843

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e24c7d923ba'
down_revision: Union[str, Sequence[str], None] = 'd3f4e5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
