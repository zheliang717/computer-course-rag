"""Persist administrator model and retrieval configuration.

Revision ID: 20260929_0017
Revises: 20260928_0016
"""
from alembic import op
import sqlalchemy as sa

revision = "20260929_0017"
down_revision = "20260928_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_runtime_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("api_base", sa.String(500), nullable=False),
        sa.Column("api_key_ciphertext", sa.Text()),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("fallback_offline", sa.Boolean(), nullable=False),
        sa.Column("retrieval_top_k", sa.Integer(), nullable=False),
        sa.Column("retrieval_min_score", sa.Float(), nullable=False),
        sa.Column("retrieval_vector_weight", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("model_runtime_config")
