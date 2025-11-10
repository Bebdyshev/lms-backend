"""fix_favorite_flashcards_cascade_delete

Revision ID: bc6c5c525916
Revises: f7befe9da0d3
Create Date: 2025-11-10 12:25:02.560392

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bc6c5c525916'
down_revision: Union[str, Sequence[str], None] = 'f7befe9da0d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop existing foreign key constraint
    op.drop_constraint('favorite_flashcards_step_id_fkey', 'favorite_flashcards', type_='foreignkey')
    
    # Recreate with CASCADE delete
    op.create_foreign_key(
        'favorite_flashcards_step_id_fkey',
        'favorite_flashcards', 'steps',
        ['step_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop CASCADE constraint
    op.drop_constraint('favorite_flashcards_step_id_fkey', 'favorite_flashcards', type_='foreignkey')
    
    # Recreate without CASCADE
    op.create_foreign_key(
        'favorite_flashcards_step_id_fkey',
        'favorite_flashcards', 'steps',
        ['step_id'], ['id']
    )
