"""add_quiz_attempts_table

Revision ID: a1b2c3d4e5f6
Revises: ce1ef6bbb115
Create Date: 2025-11-03 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '57e19d19aae8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'quiz_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('step_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('lesson_id', sa.Integer(), nullable=False),
        sa.Column('quiz_title', sa.String(), nullable=True),
        sa.Column('total_questions', sa.Integer(), nullable=False),
        sa.Column('correct_answers', sa.Integer(), nullable=False),
        sa.Column('score_percentage', sa.Float(), nullable=False),
        sa.Column('answers', sa.Text(), nullable=True),  # JSON string of user answers
        sa.Column('time_spent_seconds', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['step_id'], ['steps.id'], ),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_quiz_attempts_id'), 'quiz_attempts', ['id'], unique=False)
    op.create_index(op.f('ix_quiz_attempts_user_id'), 'quiz_attempts', ['user_id'], unique=False)
    op.create_index(op.f('ix_quiz_attempts_step_id'), 'quiz_attempts', ['step_id'], unique=False)
    op.create_index(op.f('ix_quiz_attempts_course_id'), 'quiz_attempts', ['course_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_quiz_attempts_course_id'), table_name='quiz_attempts')
    op.drop_index(op.f('ix_quiz_attempts_step_id'), table_name='quiz_attempts')
    op.drop_index(op.f('ix_quiz_attempts_user_id'), table_name='quiz_attempts')
    op.drop_index(op.f('ix_quiz_attempts_id'), table_name='quiz_attempts')
    op.drop_table('quiz_attempts')
