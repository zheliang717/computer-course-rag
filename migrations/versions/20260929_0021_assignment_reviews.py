"""Link a teacher-confirmed, published review draft to an assignment.

Revision ID: 20260929_0021
Revises: 20260929_0020
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260929_0021"
down_revision = "20260929_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assignments", sa.Column("published_review_draft_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_assignments_published_review_draft", "assignments", "teaching_drafts",
                          ["published_review_draft_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_assignments_published_review_draft_id", "assignments", ["published_review_draft_id"])


def downgrade() -> None:
    op.drop_index("ix_assignments_published_review_draft_id", table_name="assignments")
    op.drop_constraint("fk_assignments_published_review_draft", "assignments", type_="foreignkey")
    op.drop_column("assignments", "published_review_draft_id")
