"""Add persistent RAG evaluation runs.

Revision ID: 20260918_0002
Revises: 20260918_0001
"""
from alembic import op

from migrations.legacy_schema import EVALUATION_DDL


revision = "20260918_0002"
down_revision = "20260918_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in EVALUATION_DDL:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("evaluation_runs")
