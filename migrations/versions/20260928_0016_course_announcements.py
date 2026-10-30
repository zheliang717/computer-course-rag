"""Move legacy class notices into course-wide announcements.

Revision ID: 20260928_0016
Revises: 20260923_0015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260928_0016"
down_revision = "20260923_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_announcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_course_announcements_course_id", "course_announcements", ["course_id"])
    op.create_index("ix_course_announcements_author_id", "course_announcements", ["author_id"])
    op.create_index("ix_course_announcements_published_at", "course_announcements", ["published_at"])
    op.execute("""
        INSERT INTO course_announcements (id, course_id, author_id, title, content, published_at)
        SELECT notice.id, legacy.course_id, notice.author_id, notice.title, notice.content, notice.published_at
        FROM class_announcements AS notice
        JOIN course_classes AS legacy ON legacy.id = notice.class_id
    """)


def downgrade() -> None:
    op.drop_index("ix_course_announcements_published_at", table_name="course_announcements")
    op.drop_index("ix_course_announcements_author_id", table_name="course_announcements")
    op.drop_index("ix_course_announcements_course_id", table_name="course_announcements")
    op.drop_table("course_announcements")
