"""Persist trusted assistant navigation cards with their answer.

Revision ID: 20260930_0022
Revises: 20260929_0021
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260930_0022"
down_revision = "20260929_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("question_records", sa.Column(
        "actions", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
    ))


def downgrade() -> None:
    op.drop_column("question_records", "actions")
