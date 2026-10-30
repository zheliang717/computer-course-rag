"""Add course schedule and location.

Revision ID: 20260921_0008
Revises: 20260920_0007
"""
from alembic import op
import sqlalchemy as sa


revision = "20260921_0008"
down_revision = "20260920_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("schedule", sa.String(length=200), nullable=True))
    op.add_column("courses", sa.Column("location", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("courses", "location")
    op.drop_column("courses", "schedule")
