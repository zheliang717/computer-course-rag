"""Owner-scoped idempotent practice submissions, without rewriting old attempts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '20261028_0037'
down_revision = '20261023_0036'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('practice_submission_receipts',
        sa.Column('student_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('request_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('attempt_id', UUID(as_uuid=True), sa.ForeignKey('practice_attempts.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('request_digest', sa.String(64), nullable=False),
        sa.Column('result', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade():
    op.drop_table('practice_submission_receipts')
