"""change_question_id_to_string

Revision ID: f9e8d7c6b5a4
Revises: c8f9a0b1d2e3
Create Date: 2026-01-17 23:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9e8d7c6b5a4'
down_revision: Union[str, Sequence[str], None] = 'c8f9a0b1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alter question_id from bigint to character varying
    # Using explicit cast since it's going from bigint to string
    op.alter_column('question_error_reports', 'question_id',
               existing_type=sa.BigInteger(),
               type_=sa.String(length=255),
               existing_nullable=False,
               postgresql_using='question_id::varchar')


def downgrade() -> None:
    # Revert question_id from character varying to bigint
    # We attempt to cast back to bigint, using 0 for non-numeric strings
    op.alter_column('question_error_reports', 'question_id',
               existing_type=sa.String(length=255),
               type_=sa.BigInteger(),
               existing_nullable=False,
               postgresql_using="case when question_id ~ '^[0-9]+$' then question_id::bigint else 0 end")
