"""Fenced document jobs and immutable content versions; existing text unchanged."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='20261029_0044'
down_revision='20261028_0043'
branch_labels=depends_on=None
def upgrade():
    op.add_column('documents',sa.Column('content_revision',sa.Integer(),nullable=False,server_default='0'))
    op.add_column('document_ingestion_jobs',sa.Column('base_revision',sa.Integer(),nullable=False,server_default='0'))
    op.add_column('document_ingestion_jobs',sa.Column('lease_token',sa.UUID()))
    op.add_column('document_ingestion_jobs',sa.Column('lease_until',sa.DateTime(timezone=True)))
    op.create_index('ix_document_ingestion_jobs_lease_until','document_ingestion_jobs',['lease_until'])
    op.create_table('document_versions',
        sa.Column('id',sa.UUID(),primary_key=True),
        sa.Column('document_id',sa.UUID(),sa.ForeignKey('documents.id',ondelete='CASCADE'),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('filename',sa.String(500),nullable=False),
        sa.Column('pages',JSONB(),nullable=False),sa.Column('chunks',JSONB(),nullable=False),
        sa.Column('source_payload',sa.LargeBinary()),sa.Column('preprocessing',JSONB(),nullable=False),
        sa.Column('creator_id',sa.UUID(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now()),
        sa.UniqueConstraint('document_id','revision',name='uq_document_content_version'))
    op.create_index('ix_document_versions_document_id','document_versions',['document_id'])
def downgrade():
    op.drop_table('document_versions')
    op.drop_index('ix_document_ingestion_jobs_lease_until',table_name='document_ingestion_jobs')
    for column in ['lease_until','lease_token','base_revision']:op.drop_column('document_ingestion_jobs',column)
    op.drop_column('documents','content_revision')
