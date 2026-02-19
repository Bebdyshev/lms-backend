"""add program_week and applicable_weeks to curator tasks

Revision ID: 826a88ac3927
Revises: d1e2f3a4b5c6
Create Date: 2026-02-19 22:30:21.554432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '826a88ac3927'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('curator_task_instances', sa.Column('program_week', sa.Integer(), nullable=True))
    op.add_column('curator_task_templates', sa.Column('applicable_from_week', sa.Integer(), nullable=True))
    op.add_column('curator_task_templates', sa.Column('applicable_to_week', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('curator_task_templates', 'applicable_to_week')
    op.drop_column('curator_task_templates', 'applicable_from_week')
    op.drop_column('curator_task_instances', 'program_week')
