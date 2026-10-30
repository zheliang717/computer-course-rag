"""Link explicitly prepared assignments to their published question draft."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20261019_0028"
down_revision = "20261019_0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("assignments", sa.Column("source_draft_id", UUID(as_uuid=True),
        sa.ForeignKey("teaching_drafts.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_assignments_source_draft_id", "assignments", ["source_draft_id"])
    op.add_column("assignments", sa.Column("workflow_request_id", UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint("uq_assignments_workflow_request", "assignments", ["workflow_request_id"])


def downgrade():
    op.drop_constraint("uq_assignments_workflow_request", "assignments", type_="unique")
    op.drop_column("assignments", "workflow_request_id")
    op.drop_index("ix_assignments_source_draft_id", table_name="assignments")
    op.drop_column("assignments", "source_draft_id")
