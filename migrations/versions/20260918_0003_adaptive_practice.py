"""Add adaptive practice attempts and retry mastery fields.

Revision ID: 20260918_0003
Revises: 20260918_0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260918_0003"
down_revision = "20260918_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wrong_questions", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("wrong_questions", sa.Column("correct_streak", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("wrong_questions", sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_wrong_questions_last_practiced_at", "wrong_questions", ["last_practiced_at"])
    op.create_table(
        "practice_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="adaptive"),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["question_id"], ["question_bank_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_practice_attempts_student_id", "practice_attempts", ["student_id"])
    op.create_index("ix_practice_attempts_question_id", "practice_attempts", ["question_id"])
    op.create_index("ix_practice_attempts_is_correct", "practice_attempts", ["is_correct"])
    op.create_index("ix_practice_attempts_source", "practice_attempts", ["source"])
    op.create_index("ix_practice_attempts_attempted_at", "practice_attempts", ["attempted_at"])


def downgrade() -> None:
    op.drop_table("practice_attempts")
    op.drop_index("ix_wrong_questions_last_practiced_at", table_name="wrong_questions")
    op.drop_column("wrong_questions", "last_practiced_at")
    op.drop_column("wrong_questions", "correct_streak")
    op.drop_column("wrong_questions", "retry_count")
