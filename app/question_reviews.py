"""Durable, exact-question advisory reviews. Never edits a draft or a grade."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, literal, select
from sqlalchemy.exc import IntegrityError

from app.answer_stream import GenerationCancelled
from app.assistant_context import AssistantContextService
from app.domain import SearchHit, TextChunk
from app.history_access import HistoryAccess, HistoryAccessChanged
from app.model_usage import ModelUsageService
from app.models import AuditLog, Chunk, Course, Document, TeachingDraft, TeachingQuestionReview, TeachingReviewDecision, User
from app.review_evidence import saved_review_view
from app.pagination import sql_page
from app.schemas import QuestionDraftItem


def canonical_question(value):
    return QuestionDraftItem.model_validate(value).model_dump(mode='json')


def question_fingerprint(value):
    return hashlib.sha256(json.dumps(canonical_question(value), sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


class QuestionReviewService:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @staticmethod
    def _draft(session, draft_id, actor_id, role, *, lock=False):
        actor = session.get(User, actor_id)
        if not actor or not actor.active or actor.role != role or role not in {'teacher', 'admin'}:
            raise LookupError('当前账号或角色已变化，请重新登录。')
        query = select(TeachingDraft).where(TeachingDraft.id == draft_id)
        draft = session.scalar(query.with_for_update() if lock else query)
        course = session.get(Course, draft.course_id) if draft else None
        if not draft or not course or role != 'admin' and (draft.creator_id != actor_id or course.owner_id != actor_id):
            raise LookupError('草稿不存在或当前用户无权复核。')
        if draft.draft_type != 'question_set':
            raise ValueError('本功能仅用于结构化题目草稿。')
        return draft

    @staticmethod
    def _question(draft, index):
        if not 1 <= index <= len(draft.questions):
            raise ValueError('题目序号已变化，请重新打开草稿。')
        return canonical_question(draft.questions[index - 1])

    @staticmethod
    def _settle(session, job, *, successful=False, error=None, usage=None):
        values = {**(job.usage_data or {}), **(usage or {})}
        ModelUsageService.finish_in_session(session, job.usage_log_id, input_text='', output_text='',
            duration_ms=(datetime.now(timezone.utc) - job.created_at).total_seconds() * 1000,
            successful=successful, error_type=error, token_counts=values.get('token_counts'),
            usage_detail=values.get('usage_detail'))

    @classmethod
    def _expire(cls, session, job):
        if job.status == 'processing' and job.lease_expires_at <= datetime.now(timezone.utc):
            job.status, job.stage = 'failed', '处理已超时'
            job.error_message = '上次处理超过恢复时限，未保存不完整建议。可重新发起。'
            job.finished_at = job.updated_at = datetime.now(timezone.utc)
            cls._settle(session, job, error='question_review_expired')

    @staticmethod
    def _sources(session, job, actor_id, role, *, external=False):
        scope = AssistantContextService.resolve_in_session(session, user_id=actor_id, role=role,
            course_id=job.answer_scope['course_id'], purpose='teaching')
        if scope['knowledge_base_ids'] != job.answer_scope['knowledge_base_ids']:
            raise HistoryAccessChanged('课程资料绑定已变化，请按最新范围重新复核。')
        hits = []
        access = HistoryAccess(actor_id, role)
        for value in job.evidence:
            document = session.scalar(select(Document).where(Document.id == UUID(value['document_id']),
                access.document(literal(value['document_id']))))
            chunk = session.get(Chunk, UUID(value['chunk_id']))
            if (not document or document.status != 'ready' or document.publication_status != 'published'
                    or str(document.knowledge_base_id) not in scope['knowledge_base_ids']
                    or not chunk or chunk.document_id != document.id
                    or hashlib.sha256(chunk.content.encode()).hexdigest() != value['content_hash']):
                raise HistoryAccessChanged('原复核资料已不可用，保存记录不代表当前可访问。')
            if external and not document.external_model_allowed:
                raise HistoryAccessChanged('资料外发资格已变化，未继续发送。')
            hits.append(SearchHit(chunk=TextChunk(chunk_id=value['chunk_id'], document_id=value['document_id'],
                document_name=value['document_name'], page_number=value['page_number'], text=value['text'],
                chapter=value.get('chapter')), score=value['score']))
        return hits

    @classmethod
    def _view(cls, session, job, draft, actor_id, role):
        try:
            stale = question_fingerprint(cls._question(draft, job.question_index)) != job.question_fingerprint
        except ValueError:
            stale = True
        available = True
        try:
            cls._sources(session, job, actor_id, role)
        except (HistoryAccessChanged, LookupError):
            available = False
        return {'id': str(job.id), 'request_id': str(job.request_id), 'draft_id': str(job.draft_id),
            'question_index': job.question_index, 'question_fingerprint': job.question_fingerprint,
            'calculation_required': bool(job.answer_scope.get('review_options', {}).get('require_calculation')),
            'question_snapshot': job.question_snapshot, 'status': job.status, 'stage': job.stage,
            'message': job.error_message or ('建议已保存，仍需教师核对。' if job.status == 'completed' else
                '正在复核，可离开后从本题回读结果。' if job.status == 'processing' else '请求已停止，未保存不完整建议。'),
            'stale': stale or not available, 'source_available': available,
            'result': saved_review_view(job.result, job.id) if job.status == 'completed' and available and job.result else None,
            'created_at': job.created_at, 'updated_at': job.updated_at, 'finished_at': job.finished_at}

    def prepare(self, *args, **kwargs):
        try:
            return self._prepare(*args, **kwargs)
        except IntegrityError:
            # A simultaneous reuse of an actor-scoped nonce across drafts can
            # race before either sees the other. Re-read the winning row once.
            return self._prepare(*args, **kwargs)

    def _prepare(self, draft_id, *, actor_id, role, actor_name, request_id, question_index,
                expected_question, scope, hits, provider, model, timeout):
        with self._session_factory() as session:
            draft = self._draft(session, draft_id, actor_id, role, lock=True)
            snapshot = self._question(draft, question_index)
            fingerprint = question_fingerprint(snapshot)
            if fingerprint != question_fingerprint(expected_question):
                raise ValueError('保存的题目已变化，未发送旧版本。请重新打开草稿。')
            existing = session.scalar(select(TeachingQuestionReview).where(
                TeachingQuestionReview.actor_id == actor_id, TeachingQuestionReview.request_id == request_id).with_for_update())
            if existing is not None:
                if (existing.draft_id != draft_id or existing.question_index != question_index or existing.question_fingerprint != fingerprint
                        or existing.answer_scope.get('review_options', {}) != scope.get('review_options', {})):
                    raise ValueError('该请求编号已用于其他题目版本，请重新发起。')
                self._expire(session, existing)
                view = self._view(session, existing, draft, actor_id, role)
                session.commit()
                return False, view
            active = session.scalars(select(TeachingQuestionReview).where(
                TeachingQuestionReview.draft_id == draft_id, TeachingQuestionReview.question_index == question_index,
                TeachingQuestionReview.status == 'processing').with_for_update()).all()
            for item in active:
                self._expire(session, item)
                if item.status == 'processing':
                    view = self._view(session, item, draft, actor_id, role)
                    session.commit()
                    return False, view
            evidence = [{
                'document_id': h.chunk.document_id, 'document_name': h.chunk.document_name,
                'page_number': h.chunk.page_number, 'chunk_id': h.chunk.chunk_id,
                'text': h.chunk.text, 'chapter': h.chunk.chapter, 'score': h.score,
                'content_hash': hashlib.sha256(h.chunk.text.encode()).hexdigest(),
            } for h in hits]
            now = datetime.now(timezone.utc)
            job = TeachingQuestionReview(id=uuid4(), request_id=request_id, draft_id=draft_id,
                actor_id=actor_id, actor_role=role, actor_name=actor_name, question_index=question_index,
                question_fingerprint=fingerprint, question_snapshot=snapshot, answer_scope=scope,
                evidence=evidence, provider=provider, model=model, status='processing', stage='正在准备本题复核…',
                usage_data={'token_counts': {'input_tokens': 0, 'output_tokens': 0},
                    'usage_detail': {'version': 1, 'quota_unit': 'user_request', 'upstream_requests': 0,
                        'tool_attempts': 0, 'token_source': 'none', 'rounds': []}},
                created_at=now, updated_at=now, lease_expires_at=now + timedelta(seconds=max(120, timeout + 60)))
            session.add(job)
            session.flush()
            self._sources(session, job, actor_id, role, external=True)
            job.usage_log_id = ModelUsageService.reserve_in_session(session, user_id=actor_id, role=role,
                feature='teaching_question_review', provider=provider, model=model)
            view = self._view(session, job, draft, actor_id, role)
            session.commit()
            return True, view

    def get(self, draft_id, job_id, *, actor_id, role):
        with self._session_factory() as session:
            draft = self._draft(session, draft_id, actor_id, role)
            job = session.scalar(select(TeachingQuestionReview).where(TeachingQuestionReview.id == job_id,
                TeachingQuestionReview.draft_id == draft_id).with_for_update())
            if not job:
                raise LookupError('复核记录不存在。')
            self._expire(session, job)
            view = self._view(session, job, draft, actor_id, role)
            session.commit()
            return view

    def list(self, draft_id, *, actor_id, role, question_index, page, page_size):
        with self._session_factory() as session:
            draft = self._draft(session, draft_id, actor_id, role)
            self._question(draft, question_index)
            query = select(TeachingQuestionReview).where(TeachingQuestionReview.draft_id == draft_id,
                TeachingQuestionReview.question_index == question_index)
            total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
            jobs = session.scalars(query.order_by(TeachingQuestionReview.created_at.desc(), TeachingQuestionReview.id.desc())
                .offset((page - 1) * page_size).limit(page_size).with_for_update()).all()
            items = []
            for job in jobs:
                self._expire(session, job)
                items.append(self._view(session, job, draft, actor_id, role))
            session.commit()
            return {'items': items, 'total': total, 'page': page, 'page_size': page_size}

    def checkpoint(self, job_id, *, sources=False):
        with self._session_factory() as session:
            job = session.scalar(select(TeachingQuestionReview).where(TeachingQuestionReview.id == job_id).with_for_update())
            if not job:
                raise GenerationCancelled()
            self._expire(session, job)
            session.commit()
            if job.status != 'processing':
                raise GenerationCancelled()
            draft = self._draft(session, job.draft_id, job.actor_id, job.actor_role)
            if question_fingerprint(self._question(draft, job.question_index)) != job.question_fingerprint:
                raise ValueError('题目已修改，已停止旧版本复核；请按最新内容重新发起。')
            hits = self._sources(session, job, job.actor_id, job.actor_role, external=True) if sources else None
            return {'draft_id': str(job.draft_id), 'question_index': job.question_index,
                'question': job.question_snapshot, 'course_title': job.answer_scope.get('course_title'), 'hits': hits,
                'require_calculation': bool(job.answer_scope.get('review_options', {}).get('require_calculation'))}

    def progress(self, job_id, *, stage=None, usage=None):
        with self._session_factory() as session:
            job = session.scalar(select(TeachingQuestionReview).where(TeachingQuestionReview.id == job_id).with_for_update())
            if not job or job.status != 'processing':
                return
            if stage:
                job.stage = stage[:200]
            if usage:
                job.usage_data = {key: usage[key] for key in ('token_counts', 'usage_detail') if key in usage}
            job.updated_at = datetime.now(timezone.utc)
            session.commit()

    def finish(self, job_id, *, result=None, usage=None, error=None):
        with self._session_factory() as session:
            found = session.get(TeachingQuestionReview, job_id)
            if not found:
                return
            # Same lock order as prepare/cancel: a draft edit cannot interleave with final save.
            session.scalar(select(TeachingDraft).where(TeachingDraft.id == found.draft_id).with_for_update())
            job = session.scalar(select(TeachingQuestionReview).where(TeachingQuestionReview.id == job_id).with_for_update())
            self._expire(session, job)
            if job.status != 'processing':
                session.commit()
                return
            if result is not None:
                self._draft(session, job.draft_id, job.actor_id, job.actor_role)
                self._sources(session, job, job.actor_id, job.actor_role)
                job.result = result
                job.status, job.stage = 'completed', '本题复核建议已保存'
                session.add(AuditLog(actor_id=job.actor_id, actor_name=job.actor_name,
                    action='ai_review_question', resource_type='teaching_draft', resource_id=str(job.draft_id),
                    detail={'review_id': str(job.id), 'question_index': job.question_index,
                        'question_fingerprint': job.question_fingerprint, 'finding_count': len(result['findings']),
                        'evidence_count': len(job.evidence), 'calculation_count': len(result['calculations']),
                        'analysis_version': result.get('analysis_version', 1),
                        'uncertain_count': sum(item.get('assessment') == 'uncertain' for item in result['findings'])}))
            else:
                job.status, job.stage = 'failed', '本题复核未完成'
                job.error_message = (error or 'AI 复核暂不可用；原题未改变，可重新发起。')[:600]
            job.finished_at = job.updated_at = datetime.now(timezone.utc)
            self._settle(session, job, successful=result is not None,
                error=None if result is not None else 'question_review_failed', usage=usage)
            session.commit()

    def cancel(self, draft_id, job_id, *, actor_id, role, actor_name):
        with self._session_factory() as session:
            draft = self._draft(session, draft_id, actor_id, role, lock=True)
            job = session.scalar(select(TeachingQuestionReview).where(TeachingQuestionReview.id == job_id,
                TeachingQuestionReview.draft_id == draft_id).with_for_update())
            if not job:
                raise LookupError('复核记录不存在。')
            self._expire(session, job)
            if job.status == 'processing':
                job.status, job.stage = 'cancelled', '已停止本题复核'
                job.finished_at = job.updated_at = datetime.now(timezone.utc)
                self._settle(session, job, error='cancelled')
                session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action='cancel_question_review',
                    resource_type='teaching_draft', resource_id=str(draft_id), detail={'review_id': str(job.id)}))
            view = self._view(session, job, draft, actor_id, role)
            session.commit()
            return view

    @classmethod
    def _decision_target(cls, session, draft_id, job_id, finding_id, actor_id, role, *, lock=False):
        draft = cls._draft(session, draft_id, actor_id, role, lock=lock)
        query = select(TeachingQuestionReview).where(TeachingQuestionReview.id == job_id,
            TeachingQuestionReview.draft_id == draft_id)
        job = session.scalar(query.with_for_update() if lock else query)
        if not job or job.status != 'completed' or not job.result:
            raise LookupError('完整复核记录不存在或暂不可处理。')
        cls._sources(session, job, actor_id, role)
        view = saved_review_view(job.result, job.id)
        finding = next((item for item in view['findings'] if item['id'] == finding_id), None)
        if not finding:
            raise LookupError('该条意见不存在，请重新读取复核结果。')
        return draft, job, finding

    @staticmethod
    def _decision_view(item):
        return {'id': str(item.id), 'review_id': str(item.review_id), 'finding_id': item.finding_id,
            'actor_name': item.actor_name, 'decision': item.decision, 'reason': item.reason,
            'question_fingerprint': item.question_fingerprint, 'created_at': item.created_at}

    def list_decisions(self, draft_id, job_id, *, finding_id, actor_id, role, page, page_size):
        with self._session_factory() as session:
            self._decision_target(session, draft_id, job_id, finding_id, actor_id, role)
            query = select(TeachingReviewDecision).where(TeachingReviewDecision.review_id == job_id,
                TeachingReviewDecision.finding_id == finding_id).order_by(
                    TeachingReviewDecision.created_at.desc(), TeachingReviewDecision.id.desc())
            return sql_page(session, query, page=page, page_size=page_size, mapper=self._decision_view)

    def record_decision(self, *args, **kwargs):
        try:
            return self._record_decision(*args, **kwargs)
        except IntegrityError:
            return self._record_decision(*args, **kwargs)

    def _record_decision(self, draft_id, job_id, *, actor_id, role, actor_name, data):
        with self._session_factory() as session:
            draft, job, finding = self._decision_target(session, draft_id, job_id,
                data['finding_id'], actor_id, role, lock=True)
            current = question_fingerprint(self._question(draft, job.question_index))
            if current != job.question_fingerprint or current != data['expected_question_fingerprint']:
                raise ValueError('题目已变化，旧意见只供回看，未记录到当前题目。')
            reason = data['reason'].strip()
            if len(reason) < 5:
                raise ValueError('请填写至少5个字的具体判断理由。')
            existing = session.scalar(select(TeachingReviewDecision).where(
                TeachingReviewDecision.actor_id == actor_id,
                TeachingReviewDecision.request_id == data['request_id']).with_for_update())
            if existing:
                if (existing.review_id != job_id or existing.finding_id != data['finding_id']
                        or existing.decision != data['decision'] or existing.reason != reason):
                    raise ValueError('该请求编号已用于其他判断，请先刷新记录。')
                return self._decision_view(existing)
            item = TeachingReviewDecision(request_id=data['request_id'], review_id=job_id,
                finding_id=data['finding_id'], actor_id=actor_id, actor_name=actor_name,
                decision=data['decision'], reason=reason, question_fingerprint=current)
            session.add(item)
            session.flush()
            session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action='review_question_finding',
                resource_type='teaching_question_review', resource_id=str(job_id), detail={
                    'decision_id': str(item.id), 'draft_id': str(draft_id), 'finding_id': item.finding_id,
                    'decision': item.decision, 'reason': reason, 'question_fingerprint': current,
                    'basis_status': finding['basis_status'], 'assessment': finding['assessment']}))
            view = self._decision_view(item)
            session.commit()
            return view
