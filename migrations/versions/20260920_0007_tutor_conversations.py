"""Add tutor conversations and answer favorites.

Revision ID: 20260920_0007
Revises: 20260920_0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260920_0007"
down_revision = "20260920_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tutor_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_id", "knowledge_base_id", "created_at", "updated_at"):
        op.create_index(f"ix_tutor_conversations_{column}", "tutor_conversations", [column])
    op.add_column("question_records", sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("question_records", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("question_records", sa.Column("favorite", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_foreign_key("fk_question_records_conversation", "question_records", "tutor_conversations", ["conversation_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_question_records_user", "question_records", "users", ["user_id"], ["id"], ondelete="SET NULL")
    for column in ("conversation_id", "user_id", "favorite"):
        op.create_index(f"ix_question_records_{column}", "question_records", [column])


def downgrade() -> None:
    for column in ("favorite", "user_id", "conversation_id"):
        op.drop_index(f"ix_question_records_{column}", table_name="question_records")
    op.drop_constraint("fk_question_records_user", "question_records", type_="foreignkey")
    op.drop_constraint("fk_question_records_conversation", "question_records", type_="foreignkey")
    op.drop_column("question_records", "favorite")
    op.drop_column("question_records", "user_id")
    op.drop_column("question_records", "conversation_id")
    op.drop_table("tutor_conversations")
