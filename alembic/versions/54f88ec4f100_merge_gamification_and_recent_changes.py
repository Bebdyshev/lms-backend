"""merge gamification and recent changes

Revision ID: 54f88ec4f100
Revises: add093927855, h2i3j4k5l6m7
Create Date: 2026-01-23 22:12:15.142817

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '54f88ec4f100'
down_revision: Union[str, Sequence[str], None] = ('add093927855', 'h2i3j4k5l6m7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
