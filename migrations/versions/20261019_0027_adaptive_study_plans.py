"""Preserve learning-plan revisions and record-grounded preferences."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261019_0027"
down_revision = "20261019_0026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("study_plans", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("study_plans", sa.Column("previous_plan_id", UUID(as_uuid=True),
        sa.ForeignKey("study_plans.id", ondelete="SET NULL")))
    for name in ("preferences", "source_context"):
        op.add_column("study_plans", sa.Column(name, JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade():
    for name in ("source_context", "preferences", "previous_plan_id", "revision"):
        op.drop_column("study_plans", name)
