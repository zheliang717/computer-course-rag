"""Durable owner-scoped answer request receipts and atomic completion."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '20261019_0029'
down_revision = '20261019_0028'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('answer_requests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('client_request_id', UUID(as_uuid=True), nullable=False),
        sa.Column('request_signature', sa.String(64)),
        sa.Column('question', sa.Text(), nullable=False, server_default=''),
        sa.Column('context', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('status', sa.String(20), nullable=False, server_default='in_progress'),
        sa.Column('history_id', UUID(as_uuid=True), sa.ForeignKey('question_records.id', ondelete='SET NULL'), unique=True),
        sa.Column('usage_log_id', UUID(as_uuid=True), sa.ForeignKey('model_usage_logs.id', ondelete='SET NULL')),
        sa.Column('response', JSONB()),
        sa.Column('error_status', sa.Integer()),
        sa.Column('error_message', sa.String(600)),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('user_id', 'client_request_id', name='uq_answer_requests_owner_client'))
    for name in ('user_id', 'status', 'created_at'):
        op.create_index(f'ix_answer_requests_{name}', 'answer_requests', [name])


def downgrade():
    op.drop_table('answer_requests')
