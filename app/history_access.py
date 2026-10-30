"""Current database grants for stored answers, applied before paging/search.

Provenance is server-written, not a permission grant. Deleted resources and
malformed identifiers never become unrestricted history. External-model
approval remains a separate check in the answer workflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Text, and_, case, cast, false, func, literal, or_, select, true, type_coerce
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID

from app.models import (Assignment, Chunk, Course, CourseEnrollment, CourseKnowledgeBase,
                        Document, KnowledgeBase, QuestionBankItem, QuestionRecord, User)


class HistoryAccessChanged(ValueError):
    pass


def _uuid(value):
    return case((value.op('~*')(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
                 cast(value, PG_UUID(as_uuid=True))), else_=None)


def _all_json(array, predicate, *, strings=False):
    safe = case((func.jsonb_typeof(array) == 'array', array), else_=literal([], type_=JSONB))
    rows = func.jsonb_array_elements(safe).table_valued('value').alias()
    value = type_coerce(rows.c.value, JSONB)
    valid = predicate(value.op('#>>', return_type=Text)(cast(literal('{}'), ARRAY(Text))) if strings else value)
    # NOT NULL is not true in SQL: explicitly reject unknown predicates.
    return and_(func.jsonb_typeof(array) == 'array', ~select(1).select_from(rows).where(
        ~func.coalesce(valid, false())).correlate_except(rows).exists())


@dataclass(frozen=True)
class HistoryAccess:
    user_id: UUID
    role: str

    def actor(self):
        return select(1).where(User.id == self.user_id, User.active.is_(True), User.role == self.role).exists()

    def course(self, identifier):
        course = Course.__table__.alias()
        grant = true() if self.role == 'admin' else course.c.owner_id == self.user_id if self.role == 'teacher' else (
            select(1).where(CourseEnrollment.course_id == course.c.id,
                CourseEnrollment.user_id == self.user_id, CourseEnrollment.status == 'active').exists()
            if self.role == 'student' else false())
        return select(1).where(course.c.id == _uuid(identifier), grant).exists()

    def base(self, identifier):
        base = KnowledgeBase.__table__.alias()
        bound = select(1).where(CourseKnowledgeBase.knowledge_base_id == base.c.id,
            self.course(cast(CourseKnowledgeBase.course_id, Text))).exists()
        grant = true() if self.role == 'admin' else or_(
            base.c.created_by == self.user_id, bound) if self.role == 'teacher' else bound if self.role == 'student' else false()
        return select(1).where(base.c.id == _uuid(identifier), grant).exists()

    def document(self, identifier):
        doc = Document.__table__.alias()
        return select(1).where(doc.c.id == _uuid(identifier), self.base(cast(doc.c.knowledge_base_id, Text)),
            doc.c.publication_status == 'published' if self.role == 'student' else true()).exists()

    def _citation(self, value, record):
        # Old citations lack UUIDs. An exact stored passage and page in the
        # recorded base proves availability; a matching book title alone does not.
        doc = Document.__table__.alias()
        chunk = Chunk.__table__.alias()
        legacy = select(1).select_from(chunk.join(doc, chunk.c.document_id == doc.c.id)).where(
            record.knowledge_base_id.is_not(None), doc.c.knowledge_base_id == record.knowledge_base_id,
            chunk.c.content == value['text'].astext,
            cast(chunk.c.page_number, Text) == value['page_number'].astext,
            self.document(cast(doc.c.id, Text))).exists()
        return case((value['document_id'].astext.is_not(None), self.document(value['document_id'].astext)), else_=legacy)

    def _action(self, value):
        kind, target = value['kind'].astext, value['target_id'].astext
        assignment = select(1).where(Assignment.id == _uuid(target), self.course(cast(Assignment.course_id, Text)),
            Assignment.status.in_(('published', 'closed')) if self.role == 'student' else true()).exists()
        question = select(1).where(QuestionBankItem.id == _uuid(target),
            self.course(cast(QuestionBankItem.course_id, Text))).exists()
        return case(
            (kind == 'admin_tasks', literal(self.role == 'admin')),
            (kind.in_(('teacher_plan', 'teacher_questions', 'course_analysis')),
             and_(literal(self.role in ('teacher', 'admin')), self.course(target))),
            (kind.in_(('course', 'study_plan')), self.course(target)),
            (kind == 'assignment', assignment), (kind == 'wrong_question', question), else_=false())

    def provenance(self, context):
        scope = context['required_scope'].astext
        return and_(context['version'].astext == '1', context['source'].astext == 'server',
            scope.in_(('owner', 'teaching', 'management')),
            or_(scope == 'owner', and_(scope == 'teaching', literal(self.role in ('teacher', 'admin'))),
                and_(scope == 'management', literal(self.role == 'admin'))),
            _all_json(context['course_ids'], self.course, strings=True),
            _all_json(context['knowledge_base_ids'], self.base, strings=True),
            _all_json(context['document_ids'], self.document, strings=True))

    def predicate(self, record=QuestionRecord, *, owner=True, review=False):
        context = record.access_context
        # Legacy platform summaries have no complete source lineage. Keep the
        # rows intact, but do not guess the missing role/course scope. Fixed
        # navigation/empty timetable templates contain no queried private data.
        empty_timetable = record.answer.op('~')(
            '^### (今天|明天)的课 · [0-9]{4}-[0-9]{2}-[0-9]{2}\n'
            '当前课程没有安排在(今天|明天)的课次。请以教师发布的课程安排为准。$')
        legacy = or_(record.model != 'platform-data', empty_timetable, record.answer.in_((
            '请先在助手中选择一门教学课程。我会核对课程学习记录，再帮你准备备课、练习或讲评草稿。',
            '请先选择教学课程，我会核对全体在课学生的成绩、提交情况和薄弱知识点，再打开综合分析。')))
        clause = and_(self.actor(), record.user_id == self.user_id if owner else true(),
            or_(record.knowledge_base_id.is_(None), self.base(cast(record.knowledge_base_id, Text))),
            _all_json(record.context_document_ids, self.document, strings=True),
            _all_json(record.citations, lambda value: self._citation(value, record)),
            _all_json(record.actions, self._action),
            case((context.is_(None), legacy), else_=self.provenance(context)))
        if review:
            # Review is a separate teacher capability, never a route around
            # personal history ownership for platform/management summaries.
            clause = and_(clause, literal(self.role in ('teacher', 'admin')),
                record.knowledge_base_id.is_not(None), record.model != 'platform-data',
                or_(context.is_(None), context['required_scope'].astext == 'owner'))
        return clause


def build_access_context(*, role, scope, course_id=None, base_id=None, document_ids=(),
                         base_ids=(), source_course_ids=(), ancestors=()):
    courses = {str(item) for item in source_course_ids}
    bases = {str(base_id)} if base_id else set()
    bases.update(str(item) for item in base_ids)
    documents = {str(item) for item in document_ids}
    if course_id:
        courses.add(str(course_id))
    required = 'management' if scope == 'management' else 'teaching' if scope == 'teaching' else 'owner'
    rank = {'owner': 0, 'teaching': 1, 'management': 2}
    for item in ancestors:
        previous = item.access_context
        if previous:
            courses.update(previous['course_ids'])
            bases.update(previous['knowledge_base_ids'])
            documents.update(previous['document_ids'])
            required = max((required, previous['required_scope']), key=rank.get)
        if item.knowledge_base_id:
            bases.add(item.knowledge_base_id)
        documents.update(item.context_document_ids)
        # Legacy source-free/general contexts are permitted by read policy;
        # legacy material contexts remain separately blocked from cloud resend.
        documents.update(c['document_id'] for c in item.citations if c.get('document_id'))
    return {'version': 1, 'source': 'server', 'actor_role': role, 'required_scope': required,
        'course_ids': sorted(courses), 'knowledge_base_ids': sorted(bases), 'document_ids': sorted(documents),
        'assistant_course_id': str(course_id) if course_id else None, 'assistant_scope': scope}
