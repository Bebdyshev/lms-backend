"""add content_hash and quiz_content_hash for quiz versioning

Revision ID: g1h2i3j4k5l6
Revises: f7befe9da0d3
Create Date: 2026-01-21 18:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g1h2i3j4k5l6'
down_revision = 'f79f2b52a182'
branch_labels = None
depends_on = None


def upgrade():
    # Add content_hash to steps table for quiz versioning
    op.add_column('steps', sa.Column('content_hash', sa.String(64), nullable=True))
    
    # Add quiz_content_hash to quiz_attempts table
    op.add_column('quiz_attempts', sa.Column('quiz_content_hash', sa.String(64), nullable=True))


def downgrade():
    # Remove quiz_content_hash from quiz_attempts table
    op.drop_column('quiz_attempts', 'quiz_content_hash')
    
    # Remove content_hash from steps table
    op.drop_column('steps', 'content_hash')
