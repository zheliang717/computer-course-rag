"""Add model usage governance logs.

Revision ID: 20260923_0011
Revises: 20260922_0010
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260923_0011"
down_revision = "20260922_0010"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("model_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(30), nullable=False), sa.Column("feature", sa.String(60), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False), sa.Column("model", sa.String(120), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Float(), nullable=False), sa.Column("successful", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))
    for column in ("user_id", "role", "feature", "provider", "model", "successful", "error_type", "created_at"):
        op.create_index(f"ix_model_usage_logs_{column}", "model_usage_logs", [column])

def downgrade() -> None:
    op.drop_table("model_usage_logs")
