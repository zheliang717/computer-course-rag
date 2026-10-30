"""Persist student practice coaching without modifying attempts or grades.

Revision ID: 20261019_0024
Revises: 20260930_0023
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261019_0024"
down_revision = "20260930_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("practice_feedback",
        sa.Column("attempt_id", UUID(as_uuid=True), sa.ForeignKey("practice_attempts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("snapshot_signature", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("analysis", JSONB(), nullable=False),
        sa.Column("model", sa.String(200)),
        sa.Column("generation_id", UUID(as_uuid=True)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("practice_feedback")
