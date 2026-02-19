"""add curator task tables

Revision ID: d1e2f3a4b5c6
Revises: merge_all_heads_001
Create Date: 2026-02-18 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'merge_all_heads_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create curator_task_templates and curator_task_instances tables."""
    # --- curator_task_templates ---
    op.create_table(
        'curator_task_templates',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('task_type', sa.String(), nullable=False),
        sa.Column('scope', sa.String(), nullable=False, server_default='student'),
        sa.Column('recurrence_rule', sa.JSON(), nullable=True),
        sa.Column('deadline_rule', sa.JSON(), nullable=True),
        sa.Column('order_index', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index(op.f('ix_curator_task_templates_id'), 'curator_task_templates', ['id'], unique=False)

    # --- curator_task_instances ---
    op.create_table(
        'curator_task_instances',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('template_id', sa.Integer(),
                  sa.ForeignKey('curator_task_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('curator_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('student_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('group_id', sa.Integer(),
                  sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result_text', sa.Text(), nullable=True),
        sa.Column('screenshot_url', sa.String(), nullable=True),
        sa.Column('week_reference', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index(op.f('ix_curator_task_instances_id'), 'curator_task_instances', ['id'], unique=False)
    op.create_index('ix_curator_task_instances_template', 'curator_task_instances', ['template_id'], unique=False)
    op.create_index('ix_curator_task_instances_curator', 'curator_task_instances', ['curator_id'], unique=False)
    op.create_index('ix_curator_task_instances_student', 'curator_task_instances', ['student_id'], unique=False)
    op.create_index('ix_curator_task_instances_group', 'curator_task_instances', ['group_id'], unique=False)
    op.create_index('ix_curator_task_instances_curator_status', 'curator_task_instances',
                    ['curator_id', 'status'], unique=False)
    op.create_index('ix_curator_task_instances_week', 'curator_task_instances',
                    ['week_reference'], unique=False)


def downgrade() -> None:
    """Drop curator task tables."""
    op.drop_index('ix_curator_task_instances_week', table_name='curator_task_instances')
    op.drop_index('ix_curator_task_instances_curator_status', table_name='curator_task_instances')
    op.drop_index('ix_curator_task_instances_group', table_name='curator_task_instances')
    op.drop_index('ix_curator_task_instances_student', table_name='curator_task_instances')
    op.drop_index('ix_curator_task_instances_curator', table_name='curator_task_instances')
    op.drop_index('ix_curator_task_instances_template', table_name='curator_task_instances')
    op.drop_index(op.f('ix_curator_task_instances_id'), table_name='curator_task_instances')
    op.drop_table('curator_task_instances')

    op.drop_index(op.f('ix_curator_task_templates_id'), table_name='curator_task_templates')
    op.drop_table('curator_task_templates')
