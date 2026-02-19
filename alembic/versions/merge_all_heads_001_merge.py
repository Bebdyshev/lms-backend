"""merge all heads before curator tasks

Revision ID: merge_all_heads_001
Revises: h2i3j4k5l6m7, c9d0e1f2a3b4, e5f6g7h8i9j0, combined_az_001, b0b9eb23d8d1
Create Date: 2026-02-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'merge_all_heads_001'
down_revision: Union[str, Sequence[str]] = ('h2i3j4k5l6m7', 'c9d0e1f2a3b4', 'e5f6g7h8i9j0', 'combined_az_001', 'b0b9eb23d8d1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
