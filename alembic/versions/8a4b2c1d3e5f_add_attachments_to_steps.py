"""add attachments to steps

Revision ID: 8a4b2c1d3e5f
Revises: 7f3c1a2a9b10
Create Date: 2025-09-12

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a4b2c1d3e5f'
down_revision = '7f3c1a2a9b10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('steps', sa.Column('attachments', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('steps', 'attachments')
