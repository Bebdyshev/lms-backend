"""merge curator-tasks and course-teacher-access heads

Revision ID: 2518438537dd
Revises: 826a88ac3927, afb792dba8db
Create Date: 2026-02-19 23:15:05.370421

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2518438537dd'
down_revision: Union[str, Sequence[str], None] = ('826a88ac3927', 'afb792dba8db')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
