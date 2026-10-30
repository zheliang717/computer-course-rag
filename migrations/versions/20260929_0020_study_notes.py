"""Persist student-private notes grounded in published course pages.

Revision ID: 20260929_0020
Revises: 20260929_0019
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260929_0020"
down_revision = "20260929_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_notes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("source_title", sa.String(500), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_study_notes_student_id", "study_notes", ["student_id"])
    op.create_index("ix_study_notes_course_id", "study_notes", ["course_id"])
    op.create_index("ix_study_notes_document_id", "study_notes", ["document_id"])
    op.create_index("ix_study_notes_created_at", "study_notes", ["created_at"])
    op.create_index("ix_study_notes_student_course_created", "study_notes", ["student_id", "course_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_study_notes_student_course_created", table_name="study_notes")
    op.drop_index("ix_study_notes_created_at", table_name="study_notes")
    op.drop_index("ix_study_notes_document_id", table_name="study_notes")
    op.drop_index("ix_study_notes_course_id", table_name="study_notes")
    op.drop_index("ix_study_notes_student_id", table_name="study_notes")
    op.drop_table("study_notes")
