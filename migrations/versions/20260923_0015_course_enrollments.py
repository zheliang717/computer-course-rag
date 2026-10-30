"""Add direct course membership and backfill legacy class enrollments.

Revision ID: 20260923_0015
Revises: 20260923_0014
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260923_0015"
down_revision = "20260923_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("course_id", "user_id", name="uq_course_enrollment_user"),
    )
    op.create_index("ix_course_enrollments_course_id", "course_enrollments", ["course_id"])
    op.create_index("ix_course_enrollments_user_id", "course_enrollments", ["user_id"])
    op.create_index("ix_course_enrollments_status", "course_enrollments", ["status"])
    op.execute("""
        INSERT INTO course_enrollments (id, course_id, user_id, status, joined_at)
        SELECT gen_random_uuid(), c.course_id, e.user_id,
               CASE WHEN bool_or(e.status = 'active') THEN 'active' ELSE 'removed' END,
               min(e.joined_at)
        FROM class_enrollments AS e
        JOIN course_classes AS c ON c.id = e.class_id
        GROUP BY c.course_id, e.user_id
    """)


def downgrade() -> None:
    op.drop_index("ix_course_enrollments_status", table_name="course_enrollments")
    op.drop_index("ix_course_enrollments_user_id", table_name="course_enrollments")
    op.drop_index("ix_course_enrollments_course_id", table_name="course_enrollments")
    op.drop_table("course_enrollments")
