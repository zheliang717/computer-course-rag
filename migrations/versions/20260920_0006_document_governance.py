"""Add document governance metadata and original pages.

Revision ID: 20260920_0006
Revises: 20260920_0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260920_0006"
down_revision = "20260920_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("version_label", sa.String(length=80), nullable=False, server_default="1.0"))
    op.add_column("documents", sa.Column("publication_status", sa.String(length=30), nullable=False, server_default="published"))
    op.create_index("ix_documents_publication_status", "documents", ["publication_status"])
    op.create_table(
        "document_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chapter", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "page_number", name="uq_document_page_number"),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])


def downgrade() -> None:
    op.drop_table("document_pages")
    op.drop_index("ix_documents_publication_status", table_name="documents")
    op.drop_column("documents", "publication_status")
    op.drop_column("documents", "version_label")
