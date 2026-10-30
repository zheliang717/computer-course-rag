"""Separate encrypted pending credentials from public operation previews."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261019_0026"
down_revision = "20261019_0025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("admin_assistant_operations", sa.Column("private_payload", JSONB(), nullable=False,
        server_default=sa.text("'{}'::jsonb")))


def downgrade():
    op.drop_column("admin_assistant_operations", "private_payload")
