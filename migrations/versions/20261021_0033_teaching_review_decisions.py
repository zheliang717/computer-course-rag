"""Keep teacher handling decisions separate from original AI evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '20261021_0033'
down_revision = '20261021_0032'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('teaching_review_decisions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('request_id', UUID(as_uuid=True), nullable=False),
        sa.Column('review_id', UUID(as_uuid=True), sa.ForeignKey('teaching_question_reviews.id', ondelete='CASCADE'), nullable=False),
        sa.Column('finding_id', sa.String(32), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('actor_name', sa.String(120), nullable=False),
        sa.Column('decision', sa.String(20), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('question_fingerprint', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('actor_id', 'request_id', name='uq_review_decisions_actor_request'))
    op.create_index('ix_review_decisions_review_finding_created', 'teaching_review_decisions', ['review_id', 'finding_id', 'created_at'])


def downgrade():
    op.drop_index('ix_review_decisions_review_finding_created', table_name='teaching_review_decisions')
    op.drop_table('teaching_review_decisions')
