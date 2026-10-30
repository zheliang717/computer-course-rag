"""Durable explicit previews, cancellation and execution receipts for administrators."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261019_0025"
down_revision = "20261019_0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("admin_assistant_operations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("expected_signature", sa.String(64), nullable=False),
        sa.Column("before", JSONB(), nullable=False), sa.Column("proposed", JSONB(), nullable=False),
        sa.Column("result", JSONB(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
    )
    for column in ("actor_id", "status", "created_at"):
        op.create_index(f"ix_admin_assistant_operations_{column}", "admin_assistant_operations", [column])


def downgrade():
    op.drop_table("admin_assistant_operations")
