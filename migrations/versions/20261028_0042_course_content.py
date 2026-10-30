"""Course content drafts, published teaching overview and optimistic revisions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20261028_0042'
down_revision = '20261028_0041'
branch_labels = depends_on = None


def upgrade():
    op.create_table('course_content_states',
        sa.Column('course_id', sa.UUID(), sa.ForeignKey('courses.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('draft', JSONB(), nullable=True),
        sa.Column('published', JSONB(), nullable=False),
        sa.Column('base_signature', sa.String(64), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table('course_content_states')
