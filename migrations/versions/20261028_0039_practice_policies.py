"""Configurable mixed practice policy; no historical attempt changes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
revision = '20261028_0039'
down_revision = '20261028_0038'
branch_labels = depends_on = None


def upgrade():
    op.create_table('course_practice_policies',
        sa.Column('course_id', UUID(), sa.ForeignKey('courses.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('settings', JSONB(), nullable=False), sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()))


def downgrade():
    op.drop_table('course_practice_policies')
