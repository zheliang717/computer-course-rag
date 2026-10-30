"""Add course governance and class announcements.

Revision ID: 20260920_0005
Revises: 20260918_0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260920_0005"
down_revision = "20260918_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("semester", sa.String(length=80), nullable=True))
    op.add_column("courses", sa.Column("cover_image_url", sa.String(length=1000), nullable=True))
    op.create_index("ix_courses_semester", "courses", ["semester"])
    op.create_table(
        "class_announcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("class_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["class_id"], ["course_classes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_class_announcements_class_id", "class_announcements", ["class_id"])
    op.create_index("ix_class_announcements_author_id", "class_announcements", ["author_id"])
    op.create_index("ix_class_announcements_published_at", "class_announcements", ["published_at"])


def downgrade() -> None:
    op.drop_table("class_announcements")
    op.drop_index("ix_courses_semester", table_name="courses")
    op.drop_column("courses", "cover_image_url")
    op.drop_column("courses", "semester")
