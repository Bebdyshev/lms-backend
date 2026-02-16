"""add substitute_teacher_ids column

Revision ID: b8c9d0e1f2a3
Revises: a7f8b9c0d1e2
Create Date: 2026-02-15 21:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7f8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('lesson_requests', sa.Column('substitute_teacher_ids', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('lesson_requests', 'substitute_teacher_ids')
