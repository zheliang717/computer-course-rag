"""Editable resource specifications independent of actual school calendar dates."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '20261028_0041'
down_revision = '20261028_0040'
branch_labels = depends_on = None


def upgrade():
    op.create_table('timetable_resource_catalogs', sa.Column('semester', sa.String(80), primary_key=True),
        sa.Column('settings', JSONB(), nullable=False), sa.Column('revision', sa.Integer(), nullable=False))


def downgrade(): op.drop_table('timetable_resource_catalogs')
