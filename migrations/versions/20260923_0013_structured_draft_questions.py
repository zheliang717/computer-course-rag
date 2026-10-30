"""Add structured questions to teaching drafts.

Revision ID: 20260923_0013
Revises: 20260923_0012
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260923_0013"
down_revision = "20260923_0012"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("teaching_drafts", sa.Column("questions", postgresql.JSONB(),
        nullable=False, server_default=sa.text("'[]'::jsonb")))

def downgrade() -> None:
    op.drop_column("teaching_drafts", "questions")
