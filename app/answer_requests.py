"""Durable arbitration for answer completion, cancellation, and safe replay."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.answer_stream import GenerationCancelled
from app.history import PersistentHistory, _from_model
from app.history_access import HistoryAccess, HistoryAccessChanged
from app.model_usage import ModelUsageService
from app.models import AnswerRequest, QuestionRecord
from app.schemas import AskResponse


class AnswerRequestService:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @staticmethod
    def _query(user_id, client_id):
        return select(AnswerRequest).where(AnswerRequest.user_id == user_id,
            AnswerRequest.client_request_id == client_id)

    @staticmethod
    def _settle_usage(session, item, *, successful=False, error_type=None, usage=None):
        values = {**(item.context or {}).get('_generation_usage', {}), **(usage or {})}
        duration = (datetime.now(timezone.utc) - item.created_at).total_seconds() * 1000
        ModelUsageService.finish_in_session(session, item.usage_log_id,
            input_text=values.get('input_text', ''), output_text=values.get('output_text', ''),
            duration_ms=values.get('duration_ms', duration), successful=successful, error_type=error_type,
            token_counts=values.get('token_counts'), usage_detail=values.get('usage_detail'))

    @classmethod
    def _expire(cls, session, item):
        if item.status == 'in_progress' and item.lease_expires_at <= datetime.now(timezone.utc):
            item.status = 'failed'
            item.error_status = 503
            item.error_message = '上次处理已超过恢复时限，未保存未完成答案。可以重新发起。'
            item.finished_at = item.updated_at = datetime.now(timezone.utc)
            cls._settle_usage(session, item, error_type='request_expired')

    @staticmethod
    def _view(item):
        return {'request_id': str(item.client_request_id), 'status': item.status, 'question': item.question,
            'context': item.context or {}, 'answer': item.response if item.status == 'completed' else None,
            'error_status': item.error_status, 'message': item.error_message or (
                '回答已完整保存，可恢复查看。' if item.status == 'completed' else '请求仍在处理中，请先核对结果，不要重复发送。'),
            'created_at': item.created_at, 'updated_at': item.updated_at, 'finished_at': item.finished_at,
            'can_retry': item.status in {'cancelled', 'failed'}}

    def open(self, user_id, client_id, payload, *, lease_seconds):
        source = {key: value for key, value in payload.items() if key != 'request_id'}
        signature = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        context = {key: source.get(key) for key in ('knowledge_base_id', 'assistant_course_id', 'assistant_scope',
            'source_document_id', 'conversation_id', 'answer_mode', 'quick_action', '_actor_role',
            'assistant_assignment_id', 'assistant_assignment_question_id')}
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            inserted = session.scalar(insert(AnswerRequest).values(id=uuid4(), user_id=user_id,
                client_request_id=client_id, request_signature=signature, question=source['question'], context=context,
                status='in_progress', lease_expires_at=now + timedelta(seconds=lease_seconds), updated_at=now)
                .on_conflict_do_nothing(constraint='uq_answer_requests_owner_client').returning(AnswerRequest.id))
            item = session.scalar(self._query(user_id, client_id).with_for_update())
            self._expire(session, item)
            if item.request_signature is None and item.status == 'cancelled':
                item.request_signature, item.question, item.context = signature, source['question'], context
            if item.request_signature is not None and item.request_signature != signature:
                raise ValueError('该请求编号已用于其他问题，请新建请求，不要重复使用编号。')
            session.commit()
            return inserted is not None, self._view(item)

    def get(self, user_id, client_id):
        with self._session_factory() as session:
            item = session.scalar(self._query(user_id, client_id).with_for_update())
            if item is None:
                return None
            self._expire(session, item)
            session.commit()
            return self._view(item)

    def cancel(self, user_id, client_id, *, reason='user', usage=None):
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            # A stop may arrive before the original POST. The owner-scoped tombstone prevents a late start.
            session.execute(insert(AnswerRequest).values(id=uuid4(), user_id=user_id,
                client_request_id=client_id, status='cancelled', question='', context={},
                error_status=409, error_message='已停止请求，未完成答案没有保存。',
                lease_expires_at=now, updated_at=now, finished_at=now)
                .on_conflict_do_nothing(constraint='uq_answer_requests_owner_client'))
            item = session.scalar(self._query(user_id, client_id).with_for_update())
            if item.status == 'in_progress':
                item.status = 'cancelled'
                item.error_status = 409
                item.error_message = ('连接已结束，未完成答案没有保存。' if reason == 'disconnect' else
                    '已停止请求，未完成答案没有保存。')
                item.updated_at = item.finished_at = now
                self._settle_usage(session, item, error_type='cancelled', usage=usage)
            session.commit()
            return self._view(item)

    def fail(self, user_id, client_id, *, status, message, usage=None):
        with self._session_factory() as session:
            item = session.scalar(self._query(user_id, client_id).with_for_update())
            if item and item.status == 'in_progress':
                item.status = 'failed'
                item.error_status = status
                item.error_message = message[:600]
                item.updated_at = item.finished_at = datetime.now(timezone.utc)
                self._settle_usage(session, item, error_type='answer_failed', usage=usage)
            session.commit()

    def progress_usage(self, user_id, client_id, values):
        """Persist counters only, never partial answer/tool arguments or prompts."""
        with self._session_factory() as session:
            item = session.scalar(self._query(user_id, client_id).with_for_update())
            if item is None or item.status != 'in_progress':
                return False
            item.context = {**(item.context or {}), '_generation_usage': {
                key: values[key] for key in ('token_counts', 'usage_detail') if key in values}}
            session.commit()
            return True

    def bind_usage(self, user_id, client_id, reservation_id):
        with self._session_factory() as session:
            item = session.scalar(self._query(user_id, client_id).with_for_update())
            if item is None:
                raise LookupError('回答请求不存在。')
            self._expire(session, item)
            item.usage_log_id = reservation_id
            if item.status != 'in_progress':
                self._settle_usage(session, item, error_type='cancelled' if item.status == 'cancelled' else 'answer_failed')
            session.commit()
            return item.status == 'in_progress'

    def complete_history(self, user_id, client_id, *, history_data, answer_mode, usage):
        with self._session_factory() as session:
            item = session.scalar(self._query(user_id, client_id).with_for_update())
            if item is None:
                raise LookupError('回答请求不存在。')
            self._expire(session, item)
            if item.status == 'completed':
                record = session.scalar(select(QuestionRecord).where(QuestionRecord.id == item.history_id,
                    HistoryAccess(user_id, item.context.get('_actor_role', '')).predicate()))
                if record is None:
                    raise HistoryAccessChanged('原回答的课程或资料范围已变化，当前不可回读。')
                return _from_model(record)
            if item.status != 'in_progress':
                session.commit()
                raise GenerationCancelled()
            values = dict(history_data)
            if values.get('user_id') != user_id:
                raise ValueError('回答记录与请求归属不一致。')
            values['knowledge_base_id'] = UUID(values['knowledge_base_id']) if values.get('knowledge_base_id') else None
            values['citations'] = [value.model_dump() if hasattr(value, 'model_dump') else value for value in values.get('citations', [])]
            record = PersistentHistory.insert_in_session(session, **values)
            response = AskResponse(accepted=record.accepted, message=record.message, citations=record.citations,
                answer=record.answer, model=record.model, answer_mode=answer_mode, history_id=str(record.id),
                conversation_id=str(record.conversation_id) if record.conversation_id else None,
                actions=record.actions or [],
                answer_scope=(record.access_context or {}).get('answer_scope'),
                calculations=(record.access_context or {}).get('calculations', []),
                answer_review=(record.access_context or {}).get('answer_review'),
                assignment_context=(record.access_context or {}).get('assignment_context')).model_dump(mode='json')
            item.history_id = record.id
            item.response = response
            item.status = 'completed'
            item.error_status = item.error_message = None
            item.updated_at = item.finished_at = datetime.now(timezone.utc)
            self._settle_usage(session, item, successful=usage.get('error_type') is None,
                error_type=usage.get('error_type'), usage=usage)
            # Completion owns this row lock; cancellation cannot interleave between history and settlement.
            session.commit()
            return _from_model(record)


class AnswerLifecycle:
    """One worker's lightweight cancellation checks; the database is the final arbiter."""
    def __init__(self, service, user_id, request_id, answer_mode):
        self.service, self.user_id, self.request_id = service, user_id, request_id
        self.answer_mode = answer_mode
        self._last_check = 0.0

    def checkpoint(self):
        now = monotonic()
        if now - self._last_check < .3:
            return
        self._last_check = now
        item = self.service.get(self.user_id, self.request_id)
        if item is None or item['status'] != 'in_progress':
            raise GenerationCancelled()

    def bind_usage(self, reservation_id):
        if not self.service.bind_usage(self.user_id, self.request_id, reservation_id):
            raise GenerationCancelled()

    def complete(self, values, usage):
        return self.service.complete_history(self.user_id, self.request_id,
            history_data=values, answer_mode=self.answer_mode, usage=usage)

    def cancel(self, reason='disconnect', usage=None):
        return self.service.cancel(self.user_id, self.request_id, reason=reason, usage=usage)

    def fail(self, status, message):
        self.service.fail(self.user_id, self.request_id, status=status, message=message)

    def progress_usage(self, values):
        return self.service.progress_usage(self.user_id, self.request_id, values)


class ActiveAnswerStreams:
    def __init__(self):
        self._lock = Lock()
        self._items = {}

    def attach(self, user_id, request_id, stream):
        with self._lock:
            self._items[(user_id, request_id)] = stream

    def detach(self, user_id, request_id, stream):
        with self._lock:
            if self._items.get((user_id, request_id)) is stream:
                self._items.pop((user_id, request_id), None)

    def cancel(self, user_id, request_id):
        with self._lock:
            stream = self._items.get((user_id, request_id))
        if stream is not None:
            stream.cancel()
