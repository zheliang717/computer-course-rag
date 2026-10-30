"""Add teacher-confirmed AI teaching drafts.

Revision ID: 20260922_0010
Revises: 20260921_0009
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260922_0010"
down_revision = "20260921_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("teaching_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("creator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("draft_type", sa.String(40), nullable=False), sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False), sa.Column("source_context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))
    for column in ("course_id", "creator_id", "draft_type", "status", "created_at"):
        op.create_index(f"ix_teaching_drafts_{column}", "teaching_drafts", [column])


def downgrade() -> None:
    op.drop_table("teaching_drafts")
