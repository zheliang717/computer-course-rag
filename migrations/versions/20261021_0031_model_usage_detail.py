"""Keep request-level quota and record bounded multi-call generation accounting.

Old records remain NULL: their upstream call counts are not guessed/backfilled.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261021_0031'
down_revision = '20261020_0030'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('model_usage_logs', sa.Column('usage_detail', JSONB(none_as_null=True), nullable=True))


def downgrade():
    op.drop_column('model_usage_logs', 'usage_detail')
