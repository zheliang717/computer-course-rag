from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import AnswerRequest, QuestionRecord, TutorConversation
from app.answer_modes import recorded_answer_mode
from app.history_access import HistoryAccess, HistoryAccessChanged
from app.assistant_context import AssistantContextService
from app.pagination import sql_page


@dataclass(frozen=True)
class HistoryRecord:
    id: str
    knowledge_base_id: str | None
    conversation_id: str | None
    question: str
    answer: str
    message: str
    model: str
    accepted: bool
    citations: list[dict]
    actions: list[dict] = field(default_factory=list)
    external_context_safe: bool = False
    context_document_ids: list[str] = field(default_factory=list)
    access_context: dict | None = None
    rating: int | None = None
    feedback: str | None = None
    favorite: bool = False
    created_at: datetime | None = None
    user_id: str | None = None
    answer_mode: str | None = None
    answer_mode_source: str = 'unknown'


def _from_model(record: QuestionRecord) -> HistoryRecord:
    mode = recorded_answer_mode((record.access_context or {}).get('answer_mode'))
    return HistoryRecord(
        id=str(record.id),
        knowledge_base_id=str(record.knowledge_base_id) if record.knowledge_base_id else None,
        conversation_id=str(record.conversation_id) if record.conversation_id else None,
        question=record.question,
        answer=record.answer,
        message=record.message,
        model=record.model,
        accepted=record.accepted,
        citations=list(record.citations or []),
        actions=list(record.actions or []),
        external_context_safe=record.external_context_safe,
        context_document_ids=list(record.context_document_ids or []),
        access_context=record.access_context,
        rating=record.rating,
        feedback=record.feedback,
        favorite=record.favorite,
        created_at=record.created_at,
        user_id=str(record.user_id) if record.user_id else None,
        answer_mode=mode,
        answer_mode_source='saved' if mode else 'unknown',
    )


class PersistentHistory:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _records(session, records) -> list[HistoryRecord]:
        """Read legacy modes from an owned completed receipt, in one batch.

        No history backfill and no guesses from model names, KBs or citations.
        Only already authorized history rows are supplied by the caller.
        """
        items = [_from_model(record) for record in records]
        missing = {item.id: item for item in items if item.answer_mode is None and item.user_id}
        if not missing:
            return items
        rows = session.execute(select(AnswerRequest.history_id, AnswerRequest.user_id,
            AnswerRequest.question, AnswerRequest.context['answer_mode'].as_string().label('requested_mode'),
            AnswerRequest.response['answer_mode'].as_string().label('response_mode'),
            AnswerRequest.response['history_id'].as_string().label('response_history_id'),
            AnswerRequest.response['conversation_id'].as_string().label('response_conversation_id')
        ).where(AnswerRequest.history_id.in_([UUID(value) for value in missing]),
                AnswerRequest.status == 'completed')).all()
        recovered = {}
        for row in rows:
            item = missing[str(row.history_id)]
            mode = recorded_answer_mode(row.requested_mode)
            if (mode and mode == row.response_mode and str(row.user_id) == item.user_id
                    and row.question == item.question and row.response_history_id == item.id
                    and row.response_conversation_id == item.conversation_id):
                recovered[item.id] = mode
        return [replace(item, answer_mode=recovered[item.id], answer_mode_source='request_receipt')
                if item.id in recovered else item for item in items]

    def create(
        self,
        *,
        knowledge_base_id: UUID | None,
        question: str,
        answer: str,
        message: str,
        model: str,
        accepted: bool,
        citations: list[dict],
        actions: list[dict] | None = None,
        external_context_safe: bool = False,
        context_document_ids: list[str] | None = None,
        access_context: dict | None = None,
        user_id: UUID | None = None,
        conversation_id: UUID | None = None,
    ) -> HistoryRecord:
        with self._session_factory() as session:
            record = self.insert_in_session(session,
                knowledge_base_id=knowledge_base_id,
                user_id=user_id,
                conversation_id=conversation_id,
                question=question,
                answer=answer,
                message=message,
                model=model,
                accepted=accepted,
                citations=citations,
                actions=actions or [],
                external_context_safe=external_context_safe,
                context_document_ids=context_document_ids or [],
                access_context=access_context,
            )
            session.commit()
            session.refresh(record)
            return _from_model(record)

    @staticmethod
    def insert_in_session(session, **values) -> QuestionRecord:
        record = QuestionRecord(**values)
        session.add(record)
        if values.get('conversation_id') is not None:
            conversation = session.get(TutorConversation, values['conversation_id'])
            if conversation is not None:
                conversation.updated_at = datetime.now(timezone.utc)
        session.flush()
        if record.access_context is not None:
            if record.access_context.get('answer_scope'):
                AssistantContextService.validate_in_session(session, user_id=record.user_id,
                    role=record.access_context.get('actor_role', ''), snapshot=record.access_context['answer_scope'])
            access = HistoryAccess(record.user_id, record.access_context.get('actor_role', ''))
            if not session.scalar(select(QuestionRecord.id).where(
                    QuestionRecord.id == record.id, access.predicate())):
                raise HistoryAccessChanged('课程或资料范围已变化，未保存本次回答。请刷新课程后重新提问。')
        return record

    def list(self, *, knowledge_base_id: UUID | None, limit: int, user_id: UUID | None = None,
             conversation_id: UUID | None = None, favorites_only: bool = False,
             page: int | None = None, page_size: int = 10,
             access: HistoryAccess | None = None) -> list[HistoryRecord] | dict:
        statement = select(QuestionRecord).order_by(QuestionRecord.created_at.desc(), QuestionRecord.id.desc())
        if knowledge_base_id is not None:
            statement = statement.where(QuestionRecord.knowledge_base_id == knowledge_base_id)
        if user_id is not None:
            statement = statement.where(QuestionRecord.user_id == user_id)
        if conversation_id is not None:
            statement = statement.where(QuestionRecord.conversation_id == conversation_id)
        if favorites_only:
            statement = statement.where(QuestionRecord.favorite.is_(True))
        if access is not None:
            statement = statement.where(access.predicate())
        with self._session_factory() as session:
            if page is not None:
                result = sql_page(session, statement, page=page, page_size=page_size, mapper=lambda item: item)
                result['items'] = self._records(session, result['items'])
                return result
            return self._records(session, session.scalars(statement.limit(limit)).all())

    def get(self, record_id: UUID, *, user_id: UUID | None, access: HistoryAccess | None = None):
        with self._session_factory() as session:
            record = session.scalar(self._record_query(record_id, user_id=user_id, access=access))
            return self._records(session, [record])[0] if record is not None else None

    @staticmethod
    def _record_query(record_id, *, user_id, access):
        statement = select(QuestionRecord).where(QuestionRecord.id == record_id)
        if user_id is not None:
            statement = statement.where(QuestionRecord.user_id == user_id)
        if access is not None:
            statement = statement.where(access.predicate())
        return statement

    def add_feedback(self, record_id: UUID, *, user_id: UUID | None,
                     rating: int, feedback: str | None, access: HistoryAccess | None = None) -> HistoryRecord | None:
        with self._session_factory() as session:
            record = session.scalar(self._record_query(record_id, user_id=user_id, access=access).with_for_update())
            if record is None:
                return None
            record.rating = rating
            record.feedback = feedback
            session.commit()
            session.refresh(record)
            return self._records(session, [record])[0]

    def ensure_conversation(
        self, *, conversation_id: UUID | None, user_id: UUID | None,
        knowledge_base_id: UUID | None, first_question: str,
    ) -> TutorConversation | None:
        with self._session_factory() as session:
            if conversation_id is not None:
                item = session.get(TutorConversation, conversation_id)
                if item is None or (user_id is not None and item.user_id != user_id):
                    return None
                return item
            item = TutorConversation(
                user_id=user_id, knowledge_base_id=knowledge_base_id,
                title=first_question.strip()[:80],
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    def list_conversations(self, *, user_id: UUID, limit: int = 30,
                           before: UUID | None = None, query: str = "", access: HistoryAccess | None = None) -> list[dict]:
        visible_query = select(QuestionRecord.id, QuestionRecord.conversation_id, QuestionRecord.question,
                               QuestionRecord.answer, QuestionRecord.created_at).where(QuestionRecord.user_id == user_id)
        if access is not None:
            visible_query = visible_query.where(access.predicate())
        visible = visible_query.cte('visible_history')
        stats = select(visible.c.conversation_id, func.count().label('message_count'),
            func.min(visible.c.created_at).label('created_at'), func.max(visible.c.created_at).label('updated_at')
        ).group_by(visible.c.conversation_id).subquery()
        title = select(func.substr(visible.c.question, 1, 80)).where(
            visible.c.conversation_id == TutorConversation.id).order_by(
            visible.c.created_at, visible.c.id).limit(1).correlate(TutorConversation).scalar_subquery()
        with self._session_factory() as session:
            statement = select(TutorConversation.id, TutorConversation.knowledge_base_id, title.label('title'),
                stats.c.message_count, stats.c.created_at, stats.c.updated_at).join(
                stats, stats.c.conversation_id == TutorConversation.id).where(TutorConversation.user_id == user_id)
            if query.strip():
                needle = query.strip()
                matching_message = select(visible.c.id).where(
                    visible.c.conversation_id == TutorConversation.id,
                    or_(visible.c.question.icontains(needle, autoescape=True),
                        visible.c.answer.icontains(needle, autoescape=True)),
                ).correlate(TutorConversation).exists()
                statement = statement.where(matching_message)
            if before is not None:
                cursor_time = session.scalar(select(stats.c.updated_at).where(stats.c.conversation_id == before))
                if cursor_time is None:
                    raise HistoryAccessChanged('历史范围已变化，请刷新会话列表后继续。')
                statement = statement.where(or_(
                    stats.c.updated_at < cursor_time,
                    and_(stats.c.updated_at == cursor_time, TutorConversation.id < before),
                ))
            rows = session.execute(statement.order_by(
                stats.c.updated_at.desc(), TutorConversation.id.desc()).limit(limit)).all()
            return [{
                "id": str(item.id), "knowledge_base_id": str(item.knowledge_base_id) if item.knowledge_base_id else None,
                "title": item.title, "message_count": int(item.message_count),
                "created_at": item.created_at, "updated_at": item.updated_at,
            } for item in rows]

    def conversation_context(self, conversation_id: UUID, *, user_id: UUID | None, limit: int = 4,
                             access: HistoryAccess | None = None) -> list[HistoryRecord]:
        statement = select(QuestionRecord).where(QuestionRecord.conversation_id == conversation_id)
        if user_id is not None:
            statement = statement.where(QuestionRecord.user_id == user_id)
        if access is not None:
            statement = statement.where(access.predicate())
        statement = statement.order_by(QuestionRecord.created_at.desc(), QuestionRecord.id.desc()).limit(limit)
        with self._session_factory() as session:
            items = list(session.scalars(statement).all())
            return self._records(session, reversed(items))

    def message_page(self, conversation_id: UUID, *, user_id: UUID, limit: int = 20,
                     before: UUID | None = None, access: HistoryAccess | None = None) -> dict:
        """Page backwards by immutable creation order, after current access checks.

        This read does not broaden model context or change a saved conversation.
        Each page rechecks grants; counts are current reads, not a frozen snapshot.
        """
        visible = select(QuestionRecord).where(QuestionRecord.conversation_id == conversation_id,
                                             QuestionRecord.user_id == user_id)
        if access is not None:
            visible = visible.where(access.predicate())
        with self._session_factory() as session:
            conversation = session.scalar(select(TutorConversation).where(
                TutorConversation.id == conversation_id, TutorConversation.user_id == user_id))
            if conversation is None:
                raise LookupError('会话不存在或当前不可访问。')
            total = int(session.scalar(select(func.count()).select_from(visible.subquery())) or 0)
            if not total:
                raise LookupError('此会话当前没有可访问的完整回答。')
            statement = visible
            if before is not None:
                cursor = session.scalar(visible.where(QuestionRecord.id == before))
                if cursor is None:
                    raise HistoryAccessChanged('历史范围已变化，请重新打开会话后继续读取。')
                statement = statement.where(or_(QuestionRecord.created_at < cursor.created_at,
                    and_(QuestionRecord.created_at == cursor.created_at, QuestionRecord.id < cursor.id)))
            rows = list(session.scalars(statement.order_by(
                QuestionRecord.created_at.desc(), QuestionRecord.id.desc()).limit(limit + 1)).all())
            more = len(rows) > limit
            selected = list(reversed(rows[:limit]))
            return {'conversation_id': str(conversation.id),
                'knowledge_base_id': str(conversation.knowledge_base_id) if conversation.knowledge_base_id else None,
                'items': self._records(session, selected), 'message_count': total,
                'has_more': more, 'next_before': str(selected[0].id) if more and selected else None}

    def set_favorite(self, record_id: UUID, *, user_id: UUID | None, favorite: bool,
                     access: HistoryAccess | None = None) -> HistoryRecord | None:
        with self._session_factory() as session:
            record = session.scalar(self._record_query(record_id, user_id=user_id, access=access).with_for_update())
            if record is None:
                return None
            record.favorite = favorite
            session.commit()
            session.refresh(record)
            return self._records(session, [record])[0]


class MemoryHistory:
    def __init__(self) -> None:
        self._records: list[HistoryRecord] = []
        self._conversations: dict[UUID, MemoryConversation] = {}

    def create(self, **kwargs) -> HistoryRecord:
        mode = recorded_answer_mode((kwargs.get('access_context') or {}).get('answer_mode'))
        kwargs.setdefault('answer_mode', mode)
        kwargs.setdefault('answer_mode_source', 'saved' if mode else 'unknown')
        kwargs.setdefault("actions", [])
        kwargs.setdefault("external_context_safe", False)
        kwargs.setdefault("context_document_ids", [])
        if kwargs.get("user_id") is not None:
            kwargs["user_id"] = str(kwargs["user_id"])
        if kwargs.get("knowledge_base_id") is not None:
            kwargs["knowledge_base_id"] = str(kwargs["knowledge_base_id"])
        if kwargs.get("conversation_id") is not None:
            kwargs["conversation_id"] = str(kwargs["conversation_id"])
        created_at = datetime.now(timezone.utc)
        record = HistoryRecord(id=str(uuid4()), created_at=created_at, **kwargs)
        self._records.insert(0, record)
        if record.conversation_id:
            conversation = self._conversations.get(UUID(record.conversation_id))
            if conversation is not None:
                conversation.updated_at = created_at
        return record

    def list(self, *, knowledge_base_id: UUID | None, limit: int, user_id=None, conversation_id=None,
             favorites_only: bool = False, access=None) -> list[HistoryRecord]:
        selected = self._records
        if user_id is not None:
            selected = [item for item in selected if item.user_id == str(user_id)]
        if knowledge_base_id is not None:
            selected = [item for item in selected if item.knowledge_base_id == str(knowledge_base_id)]
        if conversation_id is not None:
            selected = [item for item in selected if item.conversation_id == str(conversation_id)]
        if favorites_only:
            selected = [item for item in selected if item.favorite]
        return selected[:limit]

    def get(self, record_id, *, user_id, access=None):
        return next((item for item in self.list(knowledge_base_id=None, limit=len(self._records),
            user_id=user_id, access=access) if item.id == str(record_id)), None)

    def add_feedback(self, record_id: UUID, *, user_id: UUID | None,
                     rating: int, feedback: str | None, access=None) -> HistoryRecord | None:
        for index, record in enumerate(self._records):
            if record.id == str(record_id) and (user_id is None or record.user_id == str(user_id)):
                updated = HistoryRecord(**{**record.__dict__, "rating": rating, "feedback": feedback})
                self._records[index] = updated
                return updated
        return None

    def ensure_conversation(self, *, conversation_id, user_id, knowledge_base_id, first_question):
        if conversation_id is not None:
            item = self._conversations.get(conversation_id)
            if item is None or (user_id is not None and item.user_id != user_id):
                return None
            return item
        now = datetime.now(timezone.utc)
        item = MemoryConversation(id=uuid4(), user_id=user_id, knowledge_base_id=knowledge_base_id,
                                  title=first_question.strip()[:80], created_at=now, updated_at=now)
        self._conversations[item.id] = item
        return item

    def conversation_context(self, conversation_id, *, user_id, limit=4, access=None):
        return list(reversed(self.list(knowledge_base_id=None, limit=limit, user_id=user_id,
                                       conversation_id=conversation_id)))

    def message_page(self, conversation_id, *, user_id, limit=20, before=None, access=None):
        conversation = self._conversations.get(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise LookupError('会话不存在或当前不可访问。')
        items = sorted(self.list(knowledge_base_id=None, user_id=user_id, conversation_id=conversation_id,
                                 limit=len(self._records)), key=lambda item: (item.created_at, UUID(item.id)), reverse=True)
        total = len(items)
        if not total:
            raise LookupError('此会话当前没有可访问的完整回答。')
        if before is not None:
            cursor = next((item for item in items if item.id == str(before)), None)
            if cursor is None:
                raise HistoryAccessChanged('历史范围已变化，请重新打开会话后继续读取。')
            items = [item for item in items if (item.created_at, UUID(item.id)) < (cursor.created_at, before)]
        more = len(items) > limit
        selected = list(reversed(items[:limit]))
        return {'conversation_id': str(conversation_id),
            'knowledge_base_id': str(conversation.knowledge_base_id) if conversation.knowledge_base_id else None,
            'items': selected, 'message_count': total, 'has_more': more,
            'next_before': selected[0].id if more and selected else None}

    def list_conversations(self, *, user_id, limit=30, before=None, query="", access=None):
        owner = str(user_id) if user_id is not None else None
        populated_ids = {record.conversation_id for record in self._records
                         if record.user_id == owner and record.conversation_id}
        items = sorted((item for item in self._conversations.values()
                        if item.user_id == user_id and str(item.id) in populated_ids),
                       key=lambda item: (item.updated_at, item.id), reverse=True)
        if query.strip():
            needle = query.strip().casefold()
            matching_ids = {record.conversation_id for record in self._records
                            if record.user_id == owner and
                            (needle in record.question.casefold() or needle in record.answer.casefold())}
            items = [item for item in items if needle in item.title.casefold() or str(item.id) in matching_ids]
        if before is not None:
            cursor = self._conversations.get(before)
            if cursor is None or cursor.user_id != user_id or str(cursor.id) not in populated_ids:
                return []
            items = [item for item in items if (item.updated_at, item.id) < (cursor.updated_at, cursor.id)]
        items = items[:limit]
        return [{
            "id": str(item.id), "knowledge_base_id": str(item.knowledge_base_id) if item.knowledge_base_id else None,
            "title": item.title,
            "message_count": sum(record.conversation_id == str(item.id) for record in self._records),
            "created_at": item.created_at, "updated_at": item.updated_at,
        } for item in items]

    def set_favorite(self, record_id, *, user_id, favorite, access=None):
        for index, record in enumerate(self._records):
            if record.id == str(record_id) and (user_id is None or record.user_id == str(user_id)):
                updated = HistoryRecord(**{**record.__dict__, "favorite": favorite})
                self._records[index] = updated
                return updated
        return None


@dataclass
class MemoryConversation:
    id: UUID
    user_id: UUID | None
    knowledge_base_id: UUID | None
    title: str
    created_at: datetime
    updated_at: datetime
