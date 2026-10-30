"""Private authoring resources, recoverable workflow proposals and section archive."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
import hashlib
import json

revision = '20261028_0043'
down_revision = '20261028_0042'
branch_labels = depends_on = None


def content_signatures(add):
    """Keep valid V55 pending drafts usable; do not clear genuinely stale bases."""
    bind=op.get_bind()
    def digest(value): return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    states=bind.execute(sa.text('SELECT s.*, c.title, c.description, c.cover_image_url, c.owner_id FROM course_content_states s JOIN courses c ON c.id=s.course_id')).mappings().all()
    for row in states:
        sections=bind.execute(sa.text('SELECT id,title,description,archived FROM course_sections WHERE course_id=:id ORDER BY position,id'),{'id':row['course_id']}).mappings().all()
        points=bind.execute(sa.text('SELECT id,name,description,section_id FROM knowledge_points WHERE course_id=:id ORDER BY name,id'),{'id':row['course_id']}).mappings().all()
        bases=bind.execute(sa.text('SELECT knowledge_base_id FROM course_knowledge_bases WHERE course_id=:id'),{'id':row['course_id']}).scalars().all()
        live=dict(title=row['title'],description=row['description'] or '',cover_image_url=row['cover_image_url'] or '',
            owner_id=str(row['owner_id']) if row['owner_id'] else None,learning_objectives=row['published'].get('learning_objectives',''),
            assessment=row['published'].get('assessment',''),knowledge_base_ids=sorted(map(str,bases)),
            sections=[dict(id=str(x['id']),title=x['title'],description=x['description'] or '') for x in sections],
            knowledge_points=[dict(id=str(x['id']),name=x['name'],description=x['description'] or '',section_id=str(x['section_id']) if x['section_id'] else None) for x in points])
        old=json.loads(json.dumps(live))
        if add:
            for x,source in zip(live['sections'],sections): x['archived']=source['archived']
        else:
            for x,source in zip(old['sections'],sections): x['archived']=source['archived']
        new_signature=digest(live) if row['base_signature']==digest(old) else row['base_signature']
        draft=row['draft']
        if draft is not None:
            for section in draft.get('sections',[]):
                if add: section.setdefault('archived',False)
                else: section.pop('archived',None)
        bind.execute(sa.text('UPDATE course_content_states SET base_signature=:sig,draft=CAST(:draft AS jsonb) WHERE course_id=:id'),
            dict(sig=new_signature,draft=json.dumps(draft,ensure_ascii=False) if draft is not None else None,id=row['course_id']))


def upgrade():
    op.add_column('course_sections', sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()))
    content_signatures(True)
    op.create_table('teacher_resources',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('course_id', sa.UUID(), sa.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('creator_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(200), nullable=False), sa.Column('payload', sa.LargeBinary(), nullable=False),
        sa.Column('pages', JSONB(), nullable=False), sa.Column('status', sa.String(30), nullable=False),
        sa.Column('external_allowed', sa.Boolean(), nullable=False), sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_teacher_resources_course_id', 'teacher_resources', ['course_id'])
    op.create_table('teaching_work_results',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('task_id', sa.UUID(), sa.ForeignKey('assistant_tasks.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('course_id', sa.UUID(), sa.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('actor_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(40), nullable=False), sa.Column('content', JSONB(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False), sa.Column('status', sa.String(30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_teaching_work_results_course_id', 'teaching_work_results', ['course_id'])
    op.create_index('ix_teaching_work_results_actor_id', 'teaching_work_results', ['actor_id'])
    op.create_table('question_sources',
        sa.Column('question_id', sa.UUID(), sa.ForeignKey('question_bank_items.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('source', JSONB(), nullable=False))


def downgrade():
    op.drop_table('question_sources'); op.drop_table('teaching_work_results'); op.drop_table('teacher_resources')
    content_signatures(False)
    op.drop_column('course_sections', 'archived')
