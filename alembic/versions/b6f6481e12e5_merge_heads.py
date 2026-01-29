"""Merge heads

Revision ID: b6f6481e12e5
Revises: 35af2fb48b57, b0b9eb23d8d1
Create Date: 2026-01-29 19:39:02.416276

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6f6481e12e5'
down_revision: Union[str, Sequence[str], None] = ('35af2fb48b57', 'b0b9eb23d8d1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
