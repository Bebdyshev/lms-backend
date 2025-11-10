"""merge_heads

Revision ID: f7befe9da0d3
Revises: 01cf743da45f, e5f6g7h8i9j0
Create Date: 2025-11-10 12:24:26.944630

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7befe9da0d3'
down_revision: Union[str, Sequence[str], None] = ('01cf743da45f', 'e5f6g7h8i9j0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
