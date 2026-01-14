"""change_question_id_to_bigint

Revision ID: 4dfefac419bc
Revises: f4b8302e542d
Create Date: 2026-01-14 23:55:41.498606

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4dfefac419bc'
down_revision: Union[str, Sequence[str], None] = 'f4b8302e542d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Change question_id from Integer to BigInteger to support large question IDs
    op.alter_column('question_error_reports', 'question_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert question_id back to Integer
    op.alter_column('question_error_reports', 'question_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)
