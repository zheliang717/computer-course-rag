"""Persist exact-question AI review tasks and original calculation evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '20261021_0032'
down_revision = '20261021_0031'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('teaching_question_reviews',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('request_id', UUID(as_uuid=True), nullable=False),
        sa.Column('draft_id', UUID(as_uuid=True), sa.ForeignKey('teaching_drafts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('actor_role', sa.String(30), nullable=False),
        sa.Column('actor_name', sa.String(120), nullable=False),
        sa.Column('question_index', sa.Integer, nullable=False),
        sa.Column('question_fingerprint', sa.String(64), nullable=False),
        sa.Column('question_snapshot', JSONB, nullable=False),
        sa.Column('answer_scope', JSONB, nullable=False),
        sa.Column('evidence', JSONB, nullable=False),
        sa.Column('provider', sa.String(40), nullable=False),
        sa.Column('model', sa.String(120), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('stage', sa.String(200), nullable=False),
        sa.Column('result', JSONB(none_as_null=True), nullable=True),
        sa.Column('usage_log_id', UUID(as_uuid=True), sa.ForeignKey('model_usage_logs.id', ondelete='SET NULL')),
        sa.Column('usage_data', JSONB, nullable=False),
        sa.Column('error_message', sa.String(600)),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('actor_id', 'request_id', name='uq_question_reviews_actor_request'))
    op.create_index('ix_question_reviews_draft_question_created', 'teaching_question_reviews',
                    ['draft_id', 'question_index', 'created_at'])


def downgrade():
    op.drop_index('ix_question_reviews_draft_question_created', table_name='teaching_question_reviews')
    op.drop_table('teaching_question_reviews')
