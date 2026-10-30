"""Add daily model call quotas by role.

Revision ID: 20260923_0012
Revises: 20260923_0011
"""
from alembic import op
import sqlalchemy as sa

revision = "20260923_0012"
down_revision = "20260923_0011"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("model_quotas",
        sa.Column("role", sa.String(30), primary_key=True),
        sa.Column("daily_limit", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.bulk_insert(sa.table("model_quotas", sa.column("role", sa.String), sa.column("daily_limit", sa.Integer)),
        [{"role": "student", "daily_limit": 100}, {"role": "teacher", "daily_limit": 200}, {"role": "admin", "daily_limit": 200}])

def downgrade() -> None:
    op.drop_table("model_quotas")
