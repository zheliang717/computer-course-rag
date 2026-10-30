"""Server-resolved course/material domains for new assistant generations.

An empty course binding is deliberately different from an unspecified course.
Snapshots describe a completed answer, not a grant to retrieve or resume it.
"""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import Text, cast, func, literal, select

from app.history_access import HistoryAccess, HistoryAccessChanged
from app.models import Chunk, Course, CourseKnowledgeBase, Document, KnowledgeBase


class AssistantContextService:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def resolve(self, *, user_id, role, course_id=None, base_id=None, document_id=None, purpose=None):
        with self._session_factory() as session:
            return self.resolve_in_session(session, user_id=user_id, role=role, course_id=course_id,
                base_id=base_id, document_id=document_id, purpose=purpose)

    @staticmethod
    def resolve_in_session(session, *, user_id, role, course_id=None, base_id=None,
                           document_id=None, purpose=None):
        access = HistoryAccess(user_id, role)
        if not session.scalar(select(access.actor())):
            raise HistoryAccessChanged('当前账号或角色已变化，请重新登录。')
        course = None
        if course_id:
            course = session.scalar(select(Course).where(Course.id == UUID(str(course_id)),
                access.course(literal(str(course_id)))))
            if course is None:
                raise HistoryAccessChanged('课程不存在或当前用户无权访问。')
        bases_query = select(KnowledgeBase).where(access.base(cast(KnowledgeBase.id, Text)))
        if course is not None:
            bases_query = bases_query.join(CourseKnowledgeBase,
                CourseKnowledgeBase.knowledge_base_id == KnowledgeBase.id).where(
                    CourseKnowledgeBase.course_id == course.id)
        if base_id:
            bases_query = bases_query.where(KnowledgeBase.id == UUID(str(base_id)))
        bases = session.scalars(bases_query.order_by(KnowledgeBase.id)).all()
        if base_id and not bases:
            raise HistoryAccessChanged('所选资料库未关联当前课程或已不可访问，请重新选择。')
        base_ids = [str(item.id) for item in bases]
        document = None
        if document_id:
            document = session.scalar(select(Document).where(Document.id == UUID(str(document_id)),
                access.document(literal(str(document_id)))))
            if document is None or str(document.knowledge_base_id) not in base_ids:
                raise HistoryAccessChanged('选段资料不在当前课程资料范围内，请从课程资料重新打开。')
        ready_query = select(Document.id).where(Document.knowledge_base_id.in_([item.id for item in bases]),
            Document.publication_status == 'published', Document.status == 'ready',
            select(1).where(Chunk.document_id == Document.id, Chunk.embedding.is_not(None)).exists())
        if document is not None:
            ready_query = ready_query.where(Document.id == document.id)
        ready_ids = session.scalars(ready_query).all()
        approved_count = session.scalar(select(func.count()).select_from(Document).where(
            Document.id.in_(ready_ids), Document.external_model_allowed.is_(True))) or 0
        selection = 'library' if base_id else 'course' if course else 'available'
        domain = {'version': 1, 'role': role, 'purpose': purpose,
            'course_id': str(course.id) if course else None,
            'knowledge_base_ids': base_ids, 'selection': selection}
        # A selected book is per-turn evidence, not a different conversation.
        domain_key = hashlib.sha256(json.dumps(domain, sort_keys=True).encode()).hexdigest()
        notice = ('本课程暂未关联资料；课程优先模式可作通用讲解，不会引用其他课程资料。'
                  if course and not bases else
                  '当前范围暂无已发布且完成索引的资料。' if not ready_ids else
                  f'可检索 {len(ready_ids)} 份资料，其中 {approved_count} 份可供在线 AI 讲解。')
        return {**domain, 'domain_key': domain_key,
            'course_title': course.title if course else None,
            'course_code': course.code if course else None,
            'semester': course.semester if course else None,
            'knowledge_bases': [{'id': str(item.id), 'name': item.name} for item in bases],
            'storage_knowledge_base_id': base_ids[0] if len(base_ids) == 1 else None,
            'requested_knowledge_base_id': str(base_id) if base_id else None,
            'source_document_id': str(document.id) if document else None,
            'source_document_name': document.filename if document else None,
            'ready_document_count': len(ready_ids), 'online_document_count': approved_count,
            'notice': notice}

    @staticmethod
    def validate_in_session(session, *, user_id, role, snapshot):
        current = AssistantContextService.resolve_in_session(session, user_id=user_id, role=role,
            course_id=snapshot.get('course_id'), base_id=snapshot.get('requested_knowledge_base_id'),
            document_id=snapshot.get('source_document_id'), purpose=snapshot.get('purpose'))
        if current['domain_key'] != snapshot.get('domain_key'):
            raise HistoryAccessChanged('课程资料绑定已变化，请刷新范围后重新提问。')
        return current

    def validate(self, *, user_id, role, snapshot):
        with self._session_factory() as session:
            return self.validate_in_session(session, user_id=user_id, role=role, snapshot=snapshot)
