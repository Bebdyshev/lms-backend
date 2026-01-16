"""add_cache_tables_for_analytics

Revision ID: c8f9a0b1d2e3
Revises: f7befe9da0d3
Create Date: 2026-01-16 13:45:00.000000

This migration adds StudentCourseSummary and CourseAnalyticsCache tables
for efficient analytics queries, eliminating N+1 query patterns.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c8f9a0b1d2e3'
down_revision = '24e09c407c2f'  # Correct parent migration
branch_labels = None
depends_on = None


def upgrade():
    # Create student_course_summaries table
    op.create_table(
        'student_course_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        # Progress metrics
        sa.Column('total_steps', sa.Integer(), server_default='0'),
        sa.Column('completed_steps', sa.Integer(), server_default='0'),
        sa.Column('completion_percentage', sa.Float(), server_default='0.0'),
        # Time tracking
        sa.Column('total_time_spent_minutes', sa.Integer(), server_default='0'),
        # Assignment metrics
        sa.Column('total_assignments', sa.Integer(), server_default='0'),
        sa.Column('completed_assignments', sa.Integer(), server_default='0'),
        sa.Column('total_assignment_score', sa.Float(), server_default='0.0'),
        sa.Column('max_possible_score', sa.Float(), server_default='0.0'),
        sa.Column('average_assignment_percentage', sa.Float(), server_default='0.0'),
        # Last activity
        sa.Column('last_activity_at', sa.DateTime(), nullable=True),
        sa.Column('last_lesson_id', sa.Integer(), nullable=True),
        sa.Column('last_lesson_title', sa.String(), nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()')),
        # Foreign keys
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['last_lesson_id'], ['lessons.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_student_course_summaries_id', 'student_course_summaries', ['id'])
    op.create_index('idx_user_course_summary', 'student_course_summaries', ['user_id', 'course_id'])
    op.create_unique_constraint('uq_user_course_summary', 'student_course_summaries', ['user_id', 'course_id'])

    # Create course_analytics_cache table
    op.create_table(
        'course_analytics_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False, unique=True),
        # Student counts
        sa.Column('total_enrolled', sa.Integer(), server_default='0'),
        sa.Column('active_students_7d', sa.Integer(), server_default='0'),
        sa.Column('active_students_30d', sa.Integer(), server_default='0'),
        # Aggregate progress
        sa.Column('average_completion_percentage', sa.Float(), server_default='0.0'),
        sa.Column('average_assignment_score', sa.Float(), server_default='0.0'),
        # Content counts
        sa.Column('total_modules', sa.Integer(), server_default='0'),
        sa.Column('total_lessons', sa.Integer(), server_default='0'),
        sa.Column('total_steps', sa.Integer(), server_default='0'),
        sa.Column('total_assignments', sa.Integer(), server_default='0'),
        # Timestamps
        sa.Column('last_calculated_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        # Foreign keys
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_course_analytics_cache_id', 'course_analytics_cache', ['id'])
    op.create_index('ix_course_analytics_cache_course_id', 'course_analytics_cache', ['course_id'], unique=True)

    # Add indexes to existing tables for better query performance
    # These indexes help with the most common filter patterns in analytics
    op.create_index(
        'idx_step_progress_user_course',
        'step_progress',
        ['user_id', 'course_id'],
        if_not_exists=True
    )
    op.create_index(
        'idx_step_progress_status_completed',
        'step_progress',
        ['status'],
        postgresql_where=sa.text("status = 'completed'"),
        if_not_exists=True
    )
    op.create_index(
        'idx_enrollment_user_active',
        'enrollments',
        ['user_id', 'is_active'],
        postgresql_where=sa.text("is_active = true"),
        if_not_exists=True
    )
    op.create_index(
        'idx_assignment_submission_graded',
        'assignment_submissions',
        ['is_graded'],
        if_not_exists=True
    )


def downgrade():
    # Drop indexes on existing tables
    op.drop_index('idx_assignment_submission_graded', table_name='assignment_submissions', if_exists=True)
    op.drop_index('idx_enrollment_user_active', table_name='enrollments', if_exists=True)
    op.drop_index('idx_step_progress_status_completed', table_name='step_progress', if_exists=True)
    op.drop_index('idx_step_progress_user_course', table_name='step_progress', if_exists=True)
    
    # Drop course_analytics_cache
    op.drop_index('ix_course_analytics_cache_course_id', table_name='course_analytics_cache')
    op.drop_index('ix_course_analytics_cache_id', table_name='course_analytics_cache')
    op.drop_table('course_analytics_cache')
    
    # Drop student_course_summaries
    op.drop_constraint('uq_user_course_summary', 'student_course_summaries', type_='unique')
    op.drop_index('idx_user_course_summary', table_name='student_course_summaries')
    op.drop_index('ix_student_course_summaries_id', table_name='student_course_summaries')
    op.drop_table('student_course_summaries')
