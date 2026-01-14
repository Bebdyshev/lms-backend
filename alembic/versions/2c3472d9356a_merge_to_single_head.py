"""merge_to_single_head

Revision ID: 2c3472d9356a
Revises: 65172b7f737d, combined_az_001
Create Date: 2026-01-14 10:41:59.601768

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c3472d9356a'
down_revision: Union[str, Sequence[str], None] = ('65172b7f737d', 'combined_az_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
