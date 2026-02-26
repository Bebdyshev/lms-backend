"""add custom_title to curator_task_instances and Свой template

Revision ID: j2k3l4m5n6o7
Revises: merge_all_heads_001
Create Date: 2026-02-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'j2k3l4m5n6o7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('curator_task_instances', sa.Column('custom_title', sa.String(), nullable=True))

    # Insert "Свой" template if not exists (for manual custom tasks)
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT id FROM curator_task_templates WHERE title = 'Свой' LIMIT 1"
    ))
    if result.fetchone() is None:
        conn.execute(sa.text("""
            INSERT INTO curator_task_templates (title, description, task_type, scope, order_index, is_active, created_at, updated_at)
            VALUES ('Свой', 'Свой шаблон — введите текст задачи вручную', 'manual', 'group', 999, true, NOW(), NOW())
        """))


def downgrade() -> None:
    op.drop_column('curator_task_instances', 'custom_title')
