"""Add timetable workflow without changing existing dates or completion records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '20261023_0036'
down_revision = '20261023_0035'
branch_labels = depends_on = None


def upgrade():
    op.add_column('course_sessions', sa.Column('schedule_status', sa.String(20), nullable=False, server_default='scheduled'))
    op.add_column('course_sessions', sa.Column('revision', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('course_sessions', sa.Column('rule_id', UUID(as_uuid=True)))
    op.create_index('ix_course_sessions_rule_id', 'course_sessions', ['rule_id'])
    uid = lambda name, target, **kw: sa.Column(name, UUID(as_uuid=True), sa.ForeignKey(target, ondelete=kw.pop('ondelete', 'CASCADE')), **kw)
    pk = lambda: sa.Column('id', UUID(as_uuid=True), primary_key=True)
    stamp = lambda: sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    op.create_table('timetable_calendars', sa.Column('semester',sa.String(80),primary_key=True),sa.Column('settings',JSONB,nullable=False),sa.Column('revision',sa.Integer(),nullable=False))
    op.create_table('timetable_rules',pk(),uid('course_id','courses.id',nullable=False),sa.Column('settings',JSONB,nullable=False),uid('created_by','users.id',ondelete='SET NULL'),stamp())
    op.create_table('timetable_requests',pk(),uid('course_id','courses.id',nullable=False),uid('requester_id','users.id',nullable=False),sa.Column('kind',sa.String(20),nullable=False),sa.Column('original',JSONB,nullable=False),sa.Column('proposed',JSONB,nullable=False),sa.Column('reason',sa.String(1000),nullable=False),sa.Column('status',sa.String(20),nullable=False),sa.Column('review_reason',sa.String(1000)),uid('reviewer_id','users.id',ondelete='SET NULL'),stamp(),sa.Column('reviewed_at',sa.DateTime(timezone=True)))
    op.create_table('timetable_events',pk(),uid('course_id','courses.id',nullable=False),uid('actor_id','users.id',ondelete='SET NULL'),sa.Column('detail',JSONB,nullable=False),stamp())
    for table, columns in {'timetable_rules':['course_id'],'timetable_requests':['course_id','requester_id','status'],'timetable_events':['course_id','created_at']}.items():
        for column in columns: op.create_index(f'ix_{table}_{column}',table,[column])


def downgrade():
    for table in ['timetable_events','timetable_requests','timetable_rules','timetable_calendars']: op.drop_table(table)
    for column in ['rule_id','revision','schedule_status']: op.drop_column('course_sessions',column)
