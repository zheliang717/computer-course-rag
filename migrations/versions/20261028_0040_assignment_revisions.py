"""Immutable assignment edition snapshots and per-work assistant policy."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
revision = '20261028_0040'
down_revision = '20261028_0039'
branch_labels = depends_on = None


def upgrade():
    op.add_column('assignments', sa.Column('revision', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('assignments', sa.Column('ai_policy', sa.String(20), nullable=False, server_default='hints'))
    op.add_column('assignments', sa.Column('previous_version_id', UUID(), sa.ForeignKey('assignments.id', ondelete='SET NULL')))
    op.create_index('ix_assignments_previous_version_id', 'assignments', ['previous_version_id'])
    op.create_table('assignment_revision_snapshots',
        sa.Column('id', UUID(), primary_key=True),
        sa.Column('assignment_id', UUID(), sa.ForeignKey('assignments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False), sa.Column('actor_id', UUID(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('content', JSONB(), nullable=False), sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('assignment_id', 'revision', name='uq_assignment_revision_snapshot'))
    op.create_index('ix_assignment_revision_snapshots_assignment_id', 'assignment_revision_snapshots', ['assignment_id'])


def downgrade():
    op.drop_table('assignment_revision_snapshots')
    op.drop_index('ix_assignments_previous_version_id', 'assignments')
    op.drop_column('assignments', 'previous_version_id')
    op.drop_column('assignments', 'ai_policy')
    op.drop_column('assignments', 'revision')
