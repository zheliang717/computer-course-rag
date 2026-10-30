"""Course content editing is a draft until an explicitly confirmed publication.

Course locking serializes editor writes. A content fingerprint additionally
detects changes made through the compatible legacy routes between preview and
publication. Schedule fields are deliberately not part of this API.
"""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy import func, or_, select
from app.accounts import AccountService
from app.database import Base
from app.models import (AuditLog, Course, CourseContentState, CourseKnowledgeBase,
    CourseSection, CourseSectionReading, Document, KnowledgeBase, KnowledgePoint, QuestionBankItem, StudyPlan, User)
from app.pagination import sql_page


def signature(content):
    return sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class CourseEditorService:
    def __init__(self, sessions):
        self.sessions = sessions

    @staticmethod
    def scope(s, principal, course_id):
        actor = AccountService.actor(s, principal, {'teacher', 'admin'})
        course = s.scalar(select(Course).where(Course.id == course_id).with_for_update())
        if not course or actor.role != 'admin' and course.owner_id != actor.id:
            raise PermissionError('只能编辑自己负责的课程。')
        return actor, course

    @staticmethod
    def snapshot(s, course, state):
        published = state.published if state else {}
        sections = s.scalars(select(CourseSection).where(CourseSection.course_id == course.id).order_by(CourseSection.position, CourseSection.id)).all()
        points = s.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course.id).order_by(KnowledgePoint.name, KnowledgePoint.id)).all()
        return dict(title=course.title, description=course.description or '',
            learning_objectives=published.get('learning_objectives', ''), assessment=published.get('assessment', ''),
            cover_image_url=course.cover_image_url or '', owner_id=str(course.owner_id) if course.owner_id else None,
            sections=[dict(id=str(x.id), title=x.title, description=x.description or '', archived=x.archived) for x in sections],
            knowledge_points=[dict(id=str(x.id), name=x.name, description=x.description or '',
                section_id=str(x.section_id) if x.section_id else None) for x in points],
            knowledge_base_ids=sorted(str(x) for x in s.scalars(select(CourseKnowledgeBase.knowledge_base_id).where(CourseKnowledgeBase.course_id == course.id))))

    def envelope(self, s, course):
        state = s.get(CourseContentState, course.id)
        current = self.snapshot(s, course, state)
        current_signature = signature(current)
        library_ids = set(current['knowledge_base_ids']) | set(state.draft.get('knowledge_base_ids', []) if state and state.draft else [])
        content = deepcopy(state.draft if state and state.draft is not None else current)
        owner_name = s.scalar(select(User.display_name).where(User.id == UUID(content['owner_id']))) if content['owner_id'] else None
        return dict(course_id=str(course.id), code=course.code, semester=course.semester,
            status=course.status, revision=state.revision if state else 0,
            has_draft=bool(state and state.draft is not None),
            base_signature=state.base_signature if state and state.draft is not None else current_signature,
            stale=bool(state and state.draft is not None and state.base_signature != current_signature),
            content=content, owner_name=owner_name,
            live=current, libraries=[dict(id=str(x.id), name=x.name) for x in s.scalars(select(KnowledgeBase).where(KnowledgeBase.id.in_([UUID(x) for x in library_ids])))],
            updated_at=state.updated_at.isoformat() if state and state.updated_at else None)

    def get(self, principal, course_id):
        with self.sessions.begin() as s:
            _, course = self.scope(s, principal, course_id)
            return self.envelope(s, course)

    @staticmethod
    def available_bases(s, actor):
        query = select(KnowledgeBase)
        if actor.role != 'admin':
            bound = select(CourseKnowledgeBase.knowledge_base_id).join(Course, Course.id == CourseKnowledgeBase.course_id).where(Course.owner_id == actor.id)
            query = query.where(or_(KnowledgeBase.created_by == actor.id, KnowledgeBase.id.in_(bound)))
        return query

    def libraries(self, principal, course_id, keyword, page, page_size):
        with self.sessions.begin() as s:
            actor, _ = self.scope(s, principal, course_id)
            query = self.available_bases(s, actor)
            if keyword.strip(): query = query.where(KnowledgeBase.name.ilike('%' + keyword.strip() + '%'))
            return sql_page(s, query.order_by(KnowledgeBase.name, KnowledgeBase.id), page=page, page_size=page_size,
                mapper=lambda x: dict(id=str(x.id), name=x.name, course=x.course))

    def teachers(self, principal, course_id, keyword, page, page_size):
        with self.sessions.begin() as s:
            actor, _ = self.scope(s, principal, course_id)
            if actor.role != 'admin': raise PermissionError('只有管理员可分配授课教师。')
            query = select(User).where(User.role == 'teacher', User.active.is_(True))
            if keyword.strip(): query = query.where(or_(User.display_name.ilike('%' + keyword.strip() + '%'), User.username.ilike('%' + keyword.strip() + '%')))
            return sql_page(s, query.order_by(User.display_name, User.id), page=page, page_size=page_size,
                mapper=lambda x: dict(id=str(x.id), name=x.display_name, username=x.username))

    def validate(self, s, actor, course, content):
        if actor.role != 'admin' and content['owner_id'] != (str(course.owner_id) if course.owner_id else None):
            raise PermissionError('教师不能更换授课教师。')
        if content['owner_id'] != (str(course.owner_id) if course.owner_id else None):
            teacher = s.get(User, UUID(content['owner_id'])) if content['owner_id'] else None
            if not teacher or not teacher.active or teacher.role != 'teacher': raise ValueError('请分配一名启用的教师。')
        for model, field in ((CourseSection, 'sections'), (KnowledgePoint, 'knowledge_points')):
            ids = [UUID(x['id']) for x in content[field]]
            if len(ids) != len(set(ids)): raise ValueError('章节或知识点编号重复。')
            foreign = s.scalar(select(model.id).where(model.id.in_(ids), model.course_id != course.id).limit(1))
            if foreign: raise PermissionError('章节或知识点不能属于其他课程。')
        section_ids = {x['id'] for x in content['sections']}
        if any(x['section_id'] and x['section_id'] not in section_ids for x in content['knowledge_points']):
            raise ValueError('知识点须关联本课程保留的章节。')
        names = [x['name'] for x in content['knowledge_points']]
        if len(names) != len(set(names)): raise ValueError('知识点名称不能重复。')
        requested = {UUID(x) for x in content['knowledge_base_ids']}
        allowed = set(s.scalars(self.available_bases(s, actor).with_only_columns(KnowledgeBase.id).where(KnowledgeBase.id.in_(requested))))
        if requested != allowed: raise PermissionError('所选资料库已不可访问，请重新选择。')

    @staticmethod
    def audit(s, actor, course_id, action, **detail):
        s.add(AuditLog(actor_id=actor.id, actor_name=actor.display_name, action=action,
            resource_type='course', resource_id=str(course_id), detail=detail))

    def save(self, principal, course_id, data):
        with self.sessions.begin() as s:
            actor, course = self.scope(s, principal, course_id)
            current = self.envelope(s, course)
            if current['revision'] != data.revision or current['base_signature'] != data.base_signature or current['stale']:
                raise ValueError('课程内容已被其他操作修改，请重新读取；已有草稿可先复制保留，再放弃草稿读取最新内容。')
            content = data.content.model_dump(mode='json')
            content['knowledge_base_ids'] = sorted(set(content['knowledge_base_ids']))
            self.validate(s, actor, course, content)
            state = s.get(CourseContentState, course_id)
            if not state:
                state = CourseContentState(course_id=course_id, revision=0, published={}, base_signature=current['base_signature'])
                s.add(state)
            state.base_signature = current['base_signature']
            state.draft, state.revision = content, state.revision + 1
            self.audit(s, actor, course_id, 'save_course_content_draft', revision=state.revision)
            s.flush()
            return self.envelope(s, course)

    def discard(self, principal, course_id, revision):
        with self.sessions.begin() as s:
            actor, course = self.scope(s, principal, course_id)
            state = s.get(CourseContentState, course_id)
            if not state or state.revision != revision: raise ValueError('草稿版本已变化，请重新读取。')
            state.draft, state.revision = None, state.revision + 1
            state.base_signature = signature(self.snapshot(s, course, state))
            self.audit(s, actor, course_id, 'discard_course_content_draft', revision=state.revision)
            s.flush()
            return self.envelope(s, course)

    def publish(self, principal, course_id, revision, confirmed):
        if not confirmed: raise ValueError('请先核对内容并确认发布。')
        with self.sessions.begin() as s:
            actor, course = self.scope(s, principal, course_id)
            state = s.get(CourseContentState, course_id)
            if not state or state.draft is None or state.revision != revision: raise ValueError('草稿不存在或版本已变化，请重新读取。')
            if state.base_signature != signature(self.snapshot(s, course, state)):
                raise ValueError('已发布内容发生变化，请先核对并重新制作草稿。')
            content = deepcopy(state.draft)
            self.validate(s, actor, course, content)
            old_sections = list(s.scalars(select(CourseSection).where(CourseSection.course_id == course_id)))
            old_points = list(s.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)))
            kept_sections = {UUID(x['id']) for x in content['sections']}
            kept_points = {UUID(x['id']) for x in content['knowledge_points']}
            planned_sections = {x.get('target_id') for plan in s.scalars(select(StudyPlan).where(StudyPlan.course_id == course_id))
                for x in plan.items if x.get('kind') == 'section_preview'}
            # Do not silently cascade or detach learning/teaching history.
            for row in old_sections:
                if row.id in kept_sections: continue
                if str(row.id) in planned_sections:
                    raise ValueError(f'章节“{row.title}”已用于学习计划，不能删除；可编辑内容或调整顺序。')
                for table in Base.metadata.sorted_tables:
                    if table.name == 'knowledge_points': continue
                    for column in table.columns:
                        if any(f.target_fullname == 'course_sections.id' for f in column.foreign_keys):
                            if s.scalar(select(func.count()).select_from(table).where(column == row.id)):
                                raise ValueError(f'章节“{row.title}”已有课次、作业、题目或学习记录，不能删除；可编辑内容或调整顺序。')
            point_names = {UUID(x['id']): x['name'] for x in content['knowledge_points']}
            for row in old_points:
                if point_names.get(row.id) != row.name and s.scalar(select(QuestionBankItem.id).where(QuestionBankItem.course_id == course_id, QuestionBankItem.knowledge_point == row.name).limit(1)):
                    raise ValueError(f'知识点“{row.name}”已被题目引用，请保留名称，或先调整相关题目。')
            previous_owner = str(course.owner_id) if course.owner_id else None
            removed_bases = set(s.scalars(select(CourseKnowledgeBase.knowledge_base_id).where(CourseKnowledgeBase.course_id == course_id))) - {UUID(x) for x in content['knowledge_base_ids']}
            if removed_bases and s.scalar(select(CourseSectionReading.id).join(CourseSection, CourseSection.id == CourseSectionReading.section_id).join(Document, Document.id == CourseSectionReading.document_id).where(CourseSection.course_id == course_id, Document.knowledge_base_id.in_(removed_bases)).limit(1)):
                raise ValueError('待解除关联的资料库仍用于本课程章节阅读，请先调整章节阅读安排。')
            # Free unique positions/names before reordering and renaming.
            for index, row in enumerate(old_sections): row.position = -index - 1
            for row in old_points: row.name = '__editing_' + str(row.id)
            s.flush()
            for field in ('title', 'description', 'cover_image_url'): setattr(course, field, content[field] or None)
            course.owner_id = UUID(content['owner_id']) if content['owner_id'] else None
            for position, data in enumerate(content['sections'], 1):
                row = s.get(CourseSection, UUID(data['id']))
                if row is None:
                    row = CourseSection(id=UUID(data['id']), course_id=course_id, position=position)
                    s.add(row)
                row.title, row.description, row.position = data['title'], data['description'], position
                row.archived = data.get('archived', False)
            s.flush()
            for data in content['knowledge_points']:
                row = s.get(KnowledgePoint, UUID(data['id']))
                if row is None:
                    row = KnowledgePoint(id=UUID(data['id']), course_id=course_id)
                    s.add(row)
                row.name, row.description = data['name'], data['description']
                row.section_id = UUID(data['section_id']) if data['section_id'] else None
            for row in old_points:
                if row.id not in kept_points: s.delete(row)
            s.flush()
            for row in old_sections:
                if row.id not in kept_sections: s.delete(row)
            wanted = {UUID(x) for x in content['knowledge_base_ids']}
            bindings = list(s.scalars(select(CourseKnowledgeBase).where(CourseKnowledgeBase.course_id == course_id)))
            for row in bindings:
                if row.knowledge_base_id not in wanted: s.delete(row)
            for base_id in wanted - {x.knowledge_base_id for x in bindings}:
                s.add(CourseKnowledgeBase(course_id=course_id, knowledge_base_id=base_id))
            state.published, state.draft, state.revision = content, None, state.revision + 1
            s.flush()
            state.base_signature = signature(self.snapshot(s, course, state))
            self.audit(s, actor, course_id, 'publish_course_content', revision=state.revision,
                section_count=len(content['sections']), knowledge_point_count=len(content['knowledge_points']),
                knowledge_base_count=len(wanted), previous_owner_id=previous_owner)
            return self.envelope(s, course)
