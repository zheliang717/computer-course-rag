"""Durable operational jobs and per-device authentication sessions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='20261029_0045'
down_revision='20261029_0044'
branch_labels=depends_on=None
def upgrade():
    op.create_table('operational_tasks',sa.Column('id',sa.UUID(),primary_key=True),sa.Column('actor_id',sa.UUID(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('request_id',sa.UUID(),nullable=False,unique=True),sa.Column('kind',sa.String(40),nullable=False),sa.Column('parameters',JSONB(),nullable=False),
        sa.Column('status',sa.String(30),nullable=False),sa.Column('progress',sa.Integer(),nullable=False),sa.Column('attempt',sa.Integer(),nullable=False),
        sa.Column('lease_token',sa.UUID()),sa.Column('lease_until',sa.DateTime(timezone=True)),sa.Column('result',JSONB(),nullable=False),sa.Column('error',sa.Text()),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now()))
    op.create_index('ix_operational_tasks_actor_id','operational_tasks',['actor_id']);op.create_index('ix_operational_tasks_status','operational_tasks',['status'])
    op.create_table('auth_sessions',sa.Column('id',sa.UUID(),primary_key=True),sa.Column('user_id',sa.UUID(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('refresh_hash',sa.String(64),unique=True),sa.Column('session_version',sa.Integer(),nullable=False),sa.Column('label',sa.String(200),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('revoked_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now()),sa.Column('last_seen_at',sa.DateTime(timezone=True),server_default=sa.func.now()))
    op.create_index('ix_auth_sessions_user_id','auth_sessions',['user_id'])
    op.create_table('revoked_auth_tokens',sa.Column('token_hash',sa.String(64),primary_key=True),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_revoked_auth_tokens_expires_at','revoked_auth_tokens',['expires_at'])
def downgrade():
    op.drop_table('revoked_auth_tokens');op.drop_table('auth_sessions');op.drop_table('operational_tasks')
