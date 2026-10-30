"""Invitation registration, account recovery and revocable sessions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '20261022_0034'
down_revision = '20261021_0033'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('session_version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('users', sa.Column('contact', sa.String(200)))
    uid = lambda name, target, **kw: sa.Column(name, UUID(as_uuid=True), sa.ForeignKey(target, ondelete=kw.pop('ondelete', 'CASCADE')), **kw)
    pk = lambda: sa.Column('id', UUID(as_uuid=True), primary_key=True)
    stamp = lambda: sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    op.create_table('registration_policy', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('mode', sa.String(16), nullable=False), sa.Column('teacher_applications', sa.Boolean(), nullable=False), sa.Column('version', sa.Integer(), nullable=False))
    op.execute("INSERT INTO registration_policy (id, mode, teacher_applications, version) VALUES (1, 'invite', true, 1)")
    op.create_table('access_invites', pk(), sa.Column('code_hash', sa.String(64), unique=True, nullable=False), sa.Column('label', sa.String(120), nullable=False), sa.Column('kind', sa.String(16), nullable=False), uid('course_id','courses.id'), sa.Column('approval_required', sa.Boolean(), nullable=False), sa.Column('max_uses', sa.Integer(), nullable=False), sa.Column('uses', sa.Integer(), nullable=False), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False), sa.Column('revoked', sa.Boolean(), nullable=False), uid('created_by','users.id',ondelete='SET NULL'), stamp())
    op.create_table('course_join_requests', pk(), uid('user_id','users.id',nullable=False), uid('course_id','courses.id',nullable=False), sa.Column('status',sa.String(16),nullable=False), sa.Column('reason',sa.String(500)), stamp())
    op.create_table('teacher_applications', pk(), uid('user_id','users.id',nullable=False,unique=True), sa.Column('reason',sa.String(1000),nullable=False), sa.Column('status',sa.String(16),nullable=False), sa.Column('review_reason',sa.String(500)),stamp())
    op.create_table('password_recoveries', pk(), uid('user_id','users.id',ondelete='SET NULL'),sa.Column('username',sa.String(80),nullable=False),sa.Column('note',sa.String(500),nullable=False),sa.Column('status',sa.String(16),nullable=False),stamp())
    op.create_table('password_resets',pk(),uid('user_id','users.id',nullable=False),sa.Column('token_hash',sa.String(64),unique=True,nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('used',sa.Boolean(),nullable=False),uid('created_by','users.id',ondelete='SET NULL'))
    for table, fields in {'access_invites':['course_id'],'course_join_requests':['user_id','course_id'],'password_recoveries':['user_id'],'password_resets':['user_id']}.items():
        for field in fields: op.create_index(f'ix_{table}_{field}',table,[field])


def downgrade():
    for table in ['password_resets','password_recoveries','teacher_applications','course_join_requests','access_invites','registration_policy']: op.drop_table(table)
    op.drop_column('users','contact')
    op.drop_column('users','session_version')
