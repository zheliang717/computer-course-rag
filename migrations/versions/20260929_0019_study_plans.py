"""Persist student-private, course-scoped study plans.

Revision ID: 20260929_0019
Revises: 20260929_0018
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260929_0019"
down_revision = "20260929_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("items", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_study_plans_student_id", "study_plans", ["student_id"])
    op.create_index("ix_study_plans_course_id", "study_plans", ["course_id"])
    op.create_index("ix_study_plans_created_at", "study_plans", ["created_at"])
    op.create_index("ix_study_plans_student_course_created", "study_plans", ["student_id", "course_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_study_plans_student_course_created", table_name="study_plans")
    op.drop_index("ix_study_plans_created_at", table_name="study_plans")
    op.drop_index("ix_study_plans_course_id", table_name="study_plans")
    op.drop_index("ix_study_plans_student_id", table_name="study_plans")
    op.drop_table("study_plans")
