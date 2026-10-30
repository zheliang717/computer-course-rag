"""Chapter readings, anchored answer feedback and durable teacher tasks."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '20261028_0038'
down_revision = '20261028_0037'
branch_labels = depends_on = None


def upgrade():
    op.create_table('course_section_readings',
        sa.Column('id', UUID(), primary_key=True),
        sa.Column('section_id', UUID(), sa.ForeignKey('course_sections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', UUID(), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('creator_id', UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('first_page', sa.Integer(), nullable=False), sa.Column('last_page', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(500), nullable=False), sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('section_id', 'document_id', 'first_page', 'last_page', name='uq_section_reading_range'))
    op.create_index('ix_course_section_readings_section_id', 'course_section_readings', ['section_id'])
    op.create_index('ix_course_section_readings_document_id', 'course_section_readings', ['document_id'])
    op.create_table('answer_feedback_annotations',
        sa.Column('id', UUID(), primary_key=True),
        sa.Column('history_id', UUID(), sa.ForeignKey('question_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('answer_quote', sa.Text(), nullable=False), sa.Column('start_offset', sa.Integer(), nullable=False),
        sa.Column('end_offset', sa.Integer(), nullable=False), sa.Column('category', sa.String(30), nullable=False),
        sa.Column('comment', sa.String(2000), nullable=False), sa.Column('source_index', sa.Integer()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()))
    for col in ['history_id', 'user_id']:
        op.create_index('ix_answer_feedback_annotations_'+col, 'answer_feedback_annotations', [col])
    op.create_table('assistant_tasks',
        sa.Column('id', UUID(), primary_key=True),
        sa.Column('actor_id', UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('actor_role', sa.String(30), nullable=False),
        sa.Column('course_id', UUID(), sa.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('request_id', UUID(), nullable=False), sa.Column('kind', sa.String(40), nullable=False),
        sa.Column('request_digest', sa.String(64), nullable=False), sa.Column('payload', JSONB(), nullable=False),
        sa.Column('status', sa.String(30), nullable=False), sa.Column('stage', sa.String(200), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False), sa.Column('lease_expires_at', sa.DateTime(timezone=True)),
        sa.Column('result', JSONB(none_as_null=True)), sa.Column('error', sa.String(600)),
        sa.Column('usage_log_id', UUID(), sa.ForeignKey('model_usage_logs.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('actor_id', 'request_id', name='uq_assistant_task_actor_request'))
    for col in ['actor_id', 'course_id', 'status', 'created_at']:
        op.create_index('ix_assistant_tasks_'+col, 'assistant_tasks', [col])


def downgrade():
    op.drop_table('assistant_tasks')
    op.drop_table('answer_feedback_annotations')
    op.drop_table('course_section_readings')
