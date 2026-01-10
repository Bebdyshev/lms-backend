"""combined assignment zero migration

Revision ID: combined_az_001
Revises: 154214d8c0f4
Create Date: 2026-01-10 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'combined_az_001'
down_revision: Union[str, Sequence[str], None] = '154214d8c0f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create assignment_zero_submissions table with all fields
    op.create_table(
        'assignment_zero_submissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=False),
        sa.Column('phone_number', sa.String(), nullable=False),
        sa.Column('parent_phone_number', sa.String(), nullable=False),
        sa.Column('telegram_id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('college_board_email', sa.String(), nullable=False),
        sa.Column('college_board_password', sa.String(), nullable=False),
        sa.Column('birthday_date', sa.Date(), nullable=False),
        sa.Column('city', sa.String(), nullable=False),
        sa.Column('school_type', sa.String(), nullable=False),
        sa.Column('group_name', sa.String(), nullable=False),
        sa.Column('sat_target_date', sa.String(), nullable=False),
        sa.Column('has_passed_sat_before', sa.Boolean(), nullable=True),
        sa.Column('previous_sat_score', sa.String(), nullable=True),
        sa.Column('recent_practice_test_score', sa.String(), nullable=False),
        sa.Column('bluebook_practice_test_5_score', sa.String(), nullable=False),
        sa.Column('screenshot_url', sa.String(), nullable=True),
        # Grammar Assessment
        sa.Column('grammar_punctuation', sa.Integer(), nullable=True),
        sa.Column('grammar_noun_clauses', sa.Integer(), nullable=True),
        sa.Column('grammar_relative_clauses', sa.Integer(), nullable=True),
        sa.Column('grammar_verb_forms', sa.Integer(), nullable=True),
        sa.Column('grammar_comparisons', sa.Integer(), nullable=True),
        sa.Column('grammar_transitions', sa.Integer(), nullable=True),
        sa.Column('grammar_synthesis', sa.Integer(), nullable=True),
        # Reading Skills
        sa.Column('reading_word_in_context', sa.Integer(), nullable=True),
        sa.Column('reading_text_structure', sa.Integer(), nullable=True),
        sa.Column('reading_cross_text', sa.Integer(), nullable=True),
        sa.Column('reading_central_ideas', sa.Integer(), nullable=True),
        sa.Column('reading_inferences', sa.Integer(), nullable=True),
        # Passages
        sa.Column('passages_literary', sa.Integer(), nullable=True),
        sa.Column('passages_social_science', sa.Integer(), nullable=True),
        sa.Column('passages_humanities', sa.Integer(), nullable=True),
        sa.Column('passages_science', sa.Integer(), nullable=True),
        sa.Column('passages_poetry', sa.Integer(), nullable=True),
        # Math Topics
        sa.Column('math_topics', sa.JSON(), nullable=True),
        # Additional
        sa.Column('additional_comments', sa.Text(), nullable=True),
        sa.Column('is_draft', sa.Boolean(), nullable=True),
        sa.Column('last_saved_step', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_assignment_zero_submissions_id'), 'assignment_zero_submissions', ['id'], unique=False)
    
    # Add assignment_zero_completed fields to users table
    op.add_column('users', sa.Column('assignment_zero_completed', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('assignment_zero_completed_at', sa.DateTime(), nullable=True))
    
    # Update foreign key constraints (from first migration)
    op.drop_constraint(op.f('assignment_submissions_assignment_id_fkey'), 'assignment_submissions', type_='foreignkey')
    op.create_foreign_key(None, 'assignment_submissions', 'assignments', ['assignment_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(op.f('assignments_group_id_fkey'), 'assignments', type_='foreignkey')
    op.drop_constraint(op.f('assignments_lesson_id_fkey'), 'assignments', type_='foreignkey')
    op.create_foreign_key(None, 'assignments', 'groups', ['group_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'assignments', 'lessons', ['lesson_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(op.f('lesson_materials_lesson_id_fkey'), 'lesson_materials', type_='foreignkey')
    op.create_foreign_key(None, 'lesson_materials', 'lessons', ['lesson_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(op.f('step_progress_lesson_id_fkey'), 'step_progress', type_='foreignkey')
    op.drop_constraint(op.f('step_progress_step_id_fkey'), 'step_progress', type_='foreignkey')
    op.drop_constraint(op.f('step_progress_course_id_fkey'), 'step_progress', type_='foreignkey')
    op.create_foreign_key(None, 'step_progress', 'courses', ['course_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'step_progress', 'steps', ['step_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'step_progress', 'lessons', ['lesson_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(op.f('steps_lesson_id_fkey'), 'steps', type_='foreignkey')
    op.create_foreign_key(None, 'steps', 'lessons', ['lesson_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    """Downgrade schema."""
    # Reverse foreign key changes
    op.drop_constraint(None, 'steps', type_='foreignkey')
    op.create_foreign_key(op.f('steps_lesson_id_fkey'), 'steps', 'lessons', ['lesson_id'], ['id'])
    op.drop_constraint(None, 'step_progress', type_='foreignkey')
    op.drop_constraint(None, 'step_progress', type_='foreignkey')
    op.drop_constraint(None, 'step_progress', type_='foreignkey')
    op.create_foreign_key(op.f('step_progress_course_id_fkey'), 'step_progress', 'courses', ['course_id'], ['id'])
    op.create_foreign_key(op.f('step_progress_step_id_fkey'), 'step_progress', 'steps', ['step_id'], ['id'])
    op.create_foreign_key(op.f('step_progress_lesson_id_fkey'), 'step_progress', 'lessons', ['lesson_id'], ['id'])
    op.drop_constraint(None, 'lesson_materials', type_='foreignkey')
    op.create_foreign_key(op.f('lesson_materials_lesson_id_fkey'), 'lesson_materials', 'lessons', ['lesson_id'], ['id'])
    op.drop_constraint(None, 'assignments', type_='foreignkey')
    op.drop_constraint(None, 'assignments', type_='foreignkey')
    op.create_foreign_key(op.f('assignments_lesson_id_fkey'), 'assignments', 'lessons', ['lesson_id'], ['id'])
    op.create_foreign_key(op.f('assignments_group_id_fkey'), 'assignments', 'groups', ['group_id'], ['id'])
    op.drop_constraint(None, 'assignment_submissions', type_='foreignkey')
    op.create_foreign_key(op.f('assignment_submissions_assignment_id_fkey'), 'assignment_submissions', 'assignments', ['assignment_id'], ['id'])
    
    # Drop users columns
    op.drop_column('users', 'assignment_zero_completed_at')
    op.drop_column('users', 'assignment_zero_completed')
    
    # Drop assignment_zero_submissions table
    op.drop_index(op.f('ix_assignment_zero_submissions_id'), table_name='assignment_zero_submissions')
    op.drop_table('assignment_zero_submissions')
