"""add_schedule_config_to_groups

Revision ID: 35af2fb48b57
Revises: df96114ea1e1
Create Date: 2026-01-29 18:52:48.922030

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '35af2fb48b57'
down_revision: Union[str, Sequence[str], None] = 'df96114ea1e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('groups', sa.Column('schedule_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('groups', 'schedule_config')
