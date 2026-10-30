"""Server provenance for new answers; preserve old history without backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261020_0030'
down_revision = '20261019_0029'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('question_records', sa.Column('access_context', JSONB(none_as_null=True), nullable=True))


def downgrade():
    op.drop_column('question_records', 'access_context')
