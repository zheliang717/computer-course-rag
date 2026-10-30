"""Private, bounded profile images with optimistic concurrency revisions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '20261023_0035'
down_revision = '20261022_0034'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_avatars',
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('image', sa.LargeBinary(), nullable=True),
        sa.Column('revision', sa.String(36), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table('user_avatars')
