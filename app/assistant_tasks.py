"""Leased, fenced teacher tasks. Never replay a dispatched cloud call silently."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from threading import Event, Thread
from uuid import UUID
import httpx
from pydantic import ValidationError
from sqlalchemy import select, func
from app.accounts import AccountService, utc
from app.auth import principal_from_user
from app.models import AssistantTask, Course, User
from app.model_usage import ModelUsageService
from app.pagination import sql_page


class TaskStopped(RuntimeError):
    pass


def safe_task_failure(exc):
    """Actionable categories, never provider response bodies or raw input values."""
    if isinstance(exc,httpx.HTTPStatusError):
        code=exc.response.status_code
        text={401:'在线 AI 认证失败，请联系管理员核对模型密钥。',403:'在线 AI 拒绝本次调用，请管理员核对服务权限。',
            429:'在线 AI 暂时限流或额度不足，请稍后重试或联系管理员。'}.get(code,'在线 AI 服务暂不可用，请稍后明确重试。')
        return text,'upstream_http_'+str(code)
    if isinstance(exc,httpx.TimeoutException):return '在线 AI 响应超时，结果未保存；可缩小任务后明确重试。','upstream_timeout'
    if isinstance(exc,httpx.RequestError):return '暂时无法连接在线 AI，请稍后重试。','upstream_connection'
    if isinstance(exc,(ValidationError,json.JSONDecodeError)):
        return 'AI 建议的格式不符合要求，未执行任何修改；请缩小需求后重试。','invalid_model_result'
    return '任务未完成，请核对课程权限、资料外发许可和模型额度后重试。','task_failed'


def now(): return datetime.now(timezone.utc)


class AssistantTaskService:
    def __init__(self, sessions): self.sessions = sessions

    @staticmethod
    def public(item):
        return {key: getattr(item, key) for key in ('kind', 'status', 'stage', 'attempt', 'result', 'error', 'created_at', 'updated_at')} | {
            'title': {'teaching_draft':'备课与题目', 'assignment_review':'作业讲评', 'student_analysis':'学生作答分析', 'cohort_analysis':'课程综合学情', 'material_extract':'资料原题识别', 'course_content':'课程内容建议', 'schedule_plan':'AI 排课方案'}.get(item.kind,'教学任务') + (' · '+str(item.payload.get('_course_title',''))[:60] if item.payload.get('_course_title') else '') + (' · '+str(item.payload.get('topic',''))[:80] if item.payload.get('topic') else ''),
            'id': str(item.id), 'course_id': str(item.course_id), 'request_id': str(item.request_id)}

    def create(self, principal, request_id, payload, kind='teaching_draft'):
        encoded = json.dumps({'kind': kind, 'payload': payload}, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.sessions.begin() as s:
            actor = AccountService.actor(s, principal, {'teacher', 'admin'})
            course_id = UUID(payload['course_id'])
            course=AccountService.manager(s, actor, course_id)
            if kind in {'material_extract', 'course_content', 'schedule_plan'}:
                from app.teaching_work_schemas import TASK_SCHEMAS
                TASK_SCHEMAS[kind].model_validate(payload)
            elif kind != 'teaching_draft':
                from app.models import Assignment, AssignmentSubmission
                target = UUID(payload['target_id'])
                if kind == 'assignment_review':
                    assignment = s.get(Assignment, target)
                    if not assignment or assignment.course_id != course_id: raise ValueError('作业与课程不一致。')
                elif kind == 'student_analysis':
                    submission = s.get(AssignmentSubmission, target)
                    assignment = s.get(Assignment, submission.assignment_id) if submission else None
                    if not assignment or assignment.course_id != course_id: raise ValueError('作答与课程不一致。')
                elif kind != 'cohort_analysis' or target != course_id:
                    raise ValueError('任务类型或目标不正确。')
            item = s.scalar(select(AssistantTask).where(AssistantTask.actor_id == actor.id, AssistantTask.request_id == request_id))
            if item:
                if item.request_digest != digest: raise ValueError('任务编号已用于其他内容，请勿重复使用。')
                return self.public(item)
            active = s.scalar(select(func.count()).select_from(AssistantTask).where(AssistantTask.actor_id == actor.id,
                AssistantTask.status.in_(('queued', 'running'))))
            if active >= 3: raise ValueError('已有3项任务在等待或生成，请完成后再创建。')
            item = AssistantTask(actor_id=actor.id, actor_role=actor.role, course_id=course_id, request_id=request_id,
                kind=kind, request_digest=digest, payload={**payload,'_course_title':course.title}, status='queued', attempt=0, stage='等待开始')
            s.add(item); s.flush()
            return self.public(item)

    def list(self, principal, page=1, page_size=10):
        with self.sessions() as s:
            actor = AccountService.actor(s, principal, {'teacher', 'admin'})
            query = select(AssistantTask).join(Course).where(AssistantTask.actor_id == actor.id)
            if actor.role != 'admin': query = query.where(Course.owner_id == actor.id)
            return sql_page(s, query.order_by(AssistantTask.created_at.desc(), AssistantTask.id), page=page,
                page_size=page_size, mapper=self.public)

    def owned(self, s, principal, task_id):
        actor = AccountService.actor(s, principal, {'teacher', 'admin'})
        item = s.scalar(select(AssistantTask).where(AssistantTask.id == task_id,
            AssistantTask.actor_id == actor.id).with_for_update())
        if not item: raise PermissionError('任务不存在或无权查看。')
        AccountService.manager(s, actor, item.course_id)
        return item

    def get(self, principal, task_id):
        with self.sessions() as s:
            return self.public(self.owned(s, principal, task_id))

    def action(self, principal, task_id, action):
        with self.sessions.begin() as s:
            item = self.owned(s, principal, task_id)
            if action == 'cancel':
                if item.status in ('queued', 'running'):
                    item.status, item.stage, item.lease_expires_at = 'cancelled', ('已停止；已开始的模型请求仍计入额度，不会保存迟到结果' if item.usage_log_id else '已停止，不会保存迟到的结果'), None
                    ModelUsageService.finish_in_session(s, item.usage_log_id, input_text='', output_text='',
                        duration_ms=0, successful=False, error_type='task_cancelled')
            elif action == 'retry':
                if item.status != 'failed': raise ValueError('只有失败的任务可以重试；重试可能产生新的模型费用。')
                active = s.scalar(select(func.count()).select_from(AssistantTask).where(AssistantTask.actor_id == item.actor_id,
                    AssistantTask.status.in_(('queued', 'running'))))
                if active >= 3: raise ValueError('等待中的任务过多，请稍后重试。')
                item.status, item.stage, item.error, item.usage_log_id = 'queued', '等待重新生成', None, None
            item.updated_at = now()
            AccountService.audit(s, s.get(User, item.actor_id), 'assistant_task_' + action, item.id)
            return self.public(item)

    def recover(self):
        with self.sessions.begin() as s:
            rows = s.scalars(select(AssistantTask).where(AssistantTask.status == 'running',
                AssistantTask.lease_expires_at < now()).with_for_update(skip_locked=True)).all()
            for item in rows:
                item.status, item.stage, item.error = 'failed', '生成中断', '服务中断，结果未保存。可手动重试；已发出的模型请求可能已计费。'
                item.updated_at, item.lease_expires_at = now(), None
                ModelUsageService.finish_in_session(s, item.usage_log_id, input_text='', output_text='',
                    duration_ms=0, successful=False, error_type='interrupted')

    def claim(self):
        self.recover()
        with self.sessions.begin() as s:
            item = s.scalar(select(AssistantTask).where(AssistantTask.status == 'queued').order_by(
                AssistantTask.created_at, AssistantTask.id).with_for_update(skip_locked=True).limit(1))
            if not item: return None
            actor = s.get(User, item.actor_id)
            course = s.get(Course, item.course_id)
            if not actor or not actor.active or actor.role not in {'teacher', 'admin'} or not course or (
                    actor.role != 'admin' and course.owner_id != actor.id):
                item.status, item.error, item.stage = 'failed', '当前账号或课程权限已变化，任务未执行。', '权限已变化'
                return None
            item.actor_role = actor.role
            item.status, item.stage = 'running', '正在准备课程资料'
            item.attempt += 1
            item.updated_at, item.lease_expires_at = now(), now() + timedelta(minutes=10)
            return item.id, item.attempt, principal_from_user(actor), {**item.payload, '_task_kind': item.kind}

    def fence(self, s, principal, task_id, attempt):
        actor = AccountService.actor(s, principal, {'teacher', 'admin'})
        item = s.scalar(select(AssistantTask).where(AssistantTask.id == task_id).with_for_update())
        if not item or item.actor_id != actor.id or item.status != 'running' or item.attempt != attempt or not item.lease_expires_at or utc(item.lease_expires_at) <= now():
            raise TaskStopped('任务已停止或执行凭据已失效。')
        course = s.scalar(select(Course).where(Course.id == item.course_id).with_for_update())
        if not course or (actor.role != 'admin' and course.owner_id != actor.id): raise TaskStopped('课程权限已变化。')
        return item

    def checkpoint(self, principal, task_id, attempt, stage, usage_id=None):
        with self.sessions.begin() as s:
            item = self.fence(s, principal, task_id, attempt)
            item.stage, item.updated_at, item.lease_expires_at = stage, now(), now() + timedelta(minutes=10)
            if usage_id is not None: item.usage_log_id = usage_id

    def reserve_model(self, principal, task_id, attempt, *, feature, provider, model):
        with self.sessions.begin() as s:
            item = self.fence(s, principal, task_id, attempt)
            identifier = ModelUsageService.reserve_in_session(s, user_id=item.actor_id, role=principal.role,
                feature=feature, provider=provider, model=model)
            item.usage_log_id = identifier
            return identifier

    def fail(self, task_id, attempt, message, error_type='task_failed'):
        with self.sessions.begin() as s:
            item = s.scalar(select(AssistantTask).where(AssistantTask.id == task_id).with_for_update())
            if item and item.status == 'running' and item.attempt == attempt:
                item.status, item.stage, item.error, item.updated_at, item.lease_expires_at = 'failed', '未能完成', message[:600], now(), None
                ModelUsageService.finish_in_session(s, item.usage_log_id, input_text='', output_text='',
                    duration_ms=0, successful=False, error_type=error_type)


class AssistantTaskWorker:
    def __init__(self, service, handler):
        self.service, self.handler, self.stop_event = service, handler, Event()
        self.thread = Thread(target=self.run, daemon=True, name='teacher-draft-worker')

    def start(self): self.thread.start()
    def stop(self): self.stop_event.set(); self.thread.join(timeout=3)

    def run(self):
        while not self.stop_event.is_set():
            claimed = None
            try:
                claimed = self.service.claim()
                if claimed:
                    task_id, attempt, principal, payload = claimed
                    self.handler(payload, principal, (self.service, task_id, attempt, principal))
            except Exception as exc:
                # No provider body, question, credentials or raw exception in public errors/logs.
                if claimed:
                    message,code=safe_task_failure(exc)
                    logging.getLogger(__name__).warning('Teacher task failed: %s (%s)',type(exc).__name__,code)
                    if isinstance(exc,ValidationError):
                        # Only schema paths/categories, not model values, prompts or provider bodies.
                        fields=[(x['loc'],x['type']) for x in exc.errors(include_input=False,include_url=False)[:20]]
                        logging.getLogger(__name__).warning('Teacher task schema fields: %s',fields)
                    try: self.service.fail(claimed[0], claimed[1], message,code)
                    except Exception: logging.getLogger(__name__).warning('Could not settle teacher task')
                else: logging.getLogger(__name__).warning('Teacher task queue temporarily unavailable')
            self.stop_event.wait(1 if claimed else 3)


def task_fence(session, context):
    if context:
        service, task_id, attempt, principal = context
        return service.fence(session, principal, task_id, attempt)


def complete_task(session, context, draft_id):
    item = task_fence(session, context)
    if item:
        item.status, item.stage, item.result = 'completed', '已保存，待教师核对', {'draft_id': str(draft_id)}
        item.error, item.lease_expires_at, item.updated_at = None, None, now()
