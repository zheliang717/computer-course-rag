"""Establish the complete V0.10 platform schema baseline.

Revision ID: 20260918_0001
Revises: None
"""
from alembic import op

from migrations.legacy_schema import BASELINE_DDL


revision = "20260918_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Freeze the V0.10 baseline table set so later model additions are owned by
    # their own revisions rather than leaking into this historical revision.
    # Freeze columns and constraints too: current ORM metadata contains later FKs
    # and fields which otherwise break both dependency order and ALTER revisions.
    for statement in BASELINE_DDL:
        op.execute(statement)


def downgrade() -> None:
    # A baseline downgrade is intentionally non-destructive. Database removal
    # must be an explicit backup-aware operator action.
    pass
