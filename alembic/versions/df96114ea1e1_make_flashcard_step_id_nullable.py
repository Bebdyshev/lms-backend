"""make_flashcard_step_id_nullable

Revision ID: df96114ea1e1
Revises: 54f88ec4f100
Create Date: 2026-01-23 23:05:07.031763

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df96114ea1e1'
down_revision: Union[str, Sequence[str], None] = '54f88ec4f100'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Make step_id nullable to support vocabulary flashcards created from lookup
    op.alter_column('favorite_flashcards', 'step_id',
                    existing_type=sa.Integer(),
                    nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert step_id to non-nullable
    # Note: This will fail if there are NULL values in step_id
    op.alter_column('favorite_flashcards', 'step_id',
                    existing_type=sa.Integer(),
                    nullable=False)
