"""Track knowledge-base creator for unbound teacher materials.

Revision ID: 20260929_0018
Revises: 20260929_0017
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260929_0018"
down_revision = "20260929_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_bases", sa.Column("created_by", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_knowledge_bases_created_by", "knowledge_bases", ["created_by"])
    op.create_foreign_key("fk_knowledge_bases_created_by_users", "knowledge_bases", "users",
                          ["created_by"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_knowledge_bases_created_by_users", "knowledge_bases", type_="foreignkey")
    op.drop_index("ix_knowledge_bases_created_by", table_name="knowledge_bases")
    op.drop_column("knowledge_bases", "created_by")
