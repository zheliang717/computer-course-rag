from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.auth import hash_password
from app.pagination import sql_page
from app.models import (
    Assignment,
    AuditLog,
    Chunk,
    Course,
    CourseClass,
    CourseKnowledgeBase,
    Document,
    DocumentIngestionJob,
    KnowledgeBase,
    LoginAttempt,
    ModelUsageLog,
    QuestionBankItem,
    QuestionRecord,
    RequestLog,
    User,
)


class AdminService:
    """Administrative user management, platform metrics and audit trail."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def list_users(self, *, page: int | None = None, page_size: int = 10, inactive_only: bool = False) -> list[dict] | dict:
        with self._session_factory() as session:
            query = select(User).order_by(User.created_at, User.username, User.id)
            if inactive_only:
                query = query.where(User.active.is_(False))
            if page is not None:
                return sql_page(session, query, page=page, page_size=page_size, mapper=self._user_dict)
            users = session.scalars(query).all()
            return [self._user_dict(item) for item in users]

    def create_user(self, *, username: str, display_name: str, role: str, password: str,
                    actor_id: UUID | None = None, actor_name: str | None = None,
                    confirmed: bool = False) -> dict:
        with self._session_factory() as session:
            user = User(
                username=username.strip().lower(), display_name=display_name.strip(), role=role,
                password_hash=hash_password(password), active=True,
            )
            session.add(user)
            try:
                session.flush()
                if actor_name is not None:
                    session.add(AuditLog(
                        actor_id=actor_id, actor_name=actor_name, action="create",
                        resource_type="user", resource_id=str(user.id),
                        detail={"username": user.username, "role": user.role, "confirmed": confirmed},
                    ))
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError("用户名已经存在。") from exc
            session.refresh(user)
            return self._user_dict(user)

    def set_user_active(self, user_id: UUID, active: bool, *, actor_id: UUID | None = None,
                        actor_name: str | None = None, confirmed: bool = False) -> dict | None:
        with self._session_factory() as session:
            result = self.set_user_active_in_session(session, user_id, active, actor_id=actor_id,
                actor_name=actor_name, confirmed=confirmed)
            session.commit()
            return result

    @staticmethod
    def governance_target(session, user_id: UUID, *, lock=True):
        admins = select(User).where(User.role == "admin", User.active.is_(True)).order_by(User.id)
        active_admins = list(session.scalars(admins.with_for_update() if lock else admins))
        query = select(User).where(User.id == user_id)
        target = session.scalar(query.with_for_update() if lock else query)
        return target, len(active_admins)

    @staticmethod
    def validate_user_change(target, active_admin_count, *, active=None, role=None, actor_id=None):
        if role is not None:
            if role not in {"student", "teacher", "admin"}:
                raise ValueError("角色无效。")
            if target.role == role:
                raise ValueError("用户角色未变化。")
            if target.id == actor_id:
                raise ValueError("不能修改当前登录管理员的角色。")
        removes_admin = (active is False or (role is not None and role != "admin"))
        if target.role == "admin" and target.active and removes_admin and active_admin_count <= 1:
            raise ValueError("不能停用或移除最后一名启用管理员。")

    @classmethod
    def set_user_active_in_session(cls, session, user_id, active, *, actor_id=None,
                                   actor_name=None, confirmed=False, reason=None, operation_id=None):
        target, count = cls.governance_target(session, user_id)
        if target is None:
            return None
        cls.validate_user_change(target, count, active=active, actor_id=actor_id)
        previous = target.active
        target.active = active
        if actor_name is not None:
            session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action="activate" if active else "deactivate",
                resource_type="user", resource_id=str(user_id), detail={"username": target.username,
                    "previous_active": previous, "active": active, "confirmed": confirmed,
                    **({"reason": reason} if reason else {}),
                    **({"assistant_operation_id": operation_id} if operation_id else {})}))
        return cls._user_dict(target)

    def set_user_role(self, user_id: UUID, role: str, *, actor_id: UUID,
                      actor_name: str, reason: str) -> dict | None:
        with self._session_factory() as session:
            result = self.set_user_role_in_session(session, user_id, role, actor_id=actor_id,
                actor_name=actor_name, reason=reason)
            session.commit()
            return result

    @classmethod
    def set_user_role_in_session(cls, session, user_id, role, *, actor_id, actor_name, reason, operation_id=None):
        explanation = reason.strip()
        if len(explanation) < 5:
            raise ValueError("请填写至少 5 个字的角色修改原因。")
        target, count = cls.governance_target(session, user_id)
        if target is None:
            return None
        cls.validate_user_change(target, count, role=role, actor_id=actor_id)
        previous_role = target.role
        target.role = role
        session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action="change_role",
            resource_type="user", resource_id=str(user_id), detail={"username": target.username,
                "from_role": previous_role, "to_role": role, "reason": explanation, "confirmed": True,
                **({"assistant_operation_id": operation_id} if operation_id else {})}))
        return cls._user_dict(target)

    def metrics(self) -> dict:
        with self._session_factory() as session:
            count = lambda model: int(session.scalar(select(func.count(model.id))) or 0)
            document_status = dict(session.execute(select(Document.status, func.count(Document.id)).group_by(Document.status)).all())
            question_ratings = list(session.scalars(select(QuestionRecord.rating).where(QuestionRecord.rating.is_not(None))).all())
            return {
                "user_count": count(User), "course_count": count(Course), "class_count": count(CourseClass),
                "knowledge_base_count": count(KnowledgeBase), "document_count": count(Document),
                "indexed_chunk_count": count(Chunk), "question_count": count(QuestionBankItem),
                "assignment_count": count(Assignment), "rag_question_count": count(QuestionRecord),
                "average_feedback": round(sum(question_ratings) / len(question_ratings), 2) if question_ratings else 0.0,
                "document_status": {str(key): int(value) for key, value in document_status.items()},
            }

    def assistant_insights(self) -> list[dict]:
        """Read-only, permission-scoped operational cards; never executes mutations."""
        with self._session_factory() as session:
            missing_materials = []
            for course in session.scalars(select(Course).where(Course.status == "published").order_by(Course.title)).all():
                ready_count = session.scalar(
                    select(func.count(Document.id))
                    .join(CourseKnowledgeBase, CourseKnowledgeBase.knowledge_base_id == Document.knowledge_base_id)
                    .where(CourseKnowledgeBase.course_id == course.id, Document.status == "ready",
                           Document.publication_status == "published")
                ) or 0
                if not ready_count:
                    missing_materials.append(course.title)
            failed_jobs = int(session.scalar(select(func.count(DocumentIngestionJob.id)).where(
                DocumentIngestionJob.status == "failed")) or 0)
            since = datetime.now(timezone.utc) - timedelta(days=1)
            failed_model_calls = int(session.scalar(select(func.count(ModelUsageLog.id)).where(
                ModelUsageLog.created_at >= since, ModelUsageLog.successful.is_(False),
                ModelUsageLog.error_type.is_distinct_from("pending"),
                ModelUsageLog.error_type.is_distinct_from("cancelled"))) or 0)
            inactive_users = int(session.scalar(select(func.count(User.id)).where(User.active.is_(False))) or 0)
            cards = []
            if missing_materials:
                names = "、".join(missing_materials[:3])
                cards.append({"id": "admin-course-materials", "eyebrow": "资料治理", "title": f"{len(missing_materials)} 门课程缺少已发布资料",
                              "detail": f"涉及：{names}。请核查资料绑定和发布状态。", "button": "查看课程", "tone": "warning"})
            if failed_jobs:
                cards.append({"id": "admin-jobs", "eyebrow": "导入异常", "title": f"{failed_jobs} 个资料任务失败",
                              "detail": "查看失败原因，确认后可重试任务。", "button": "查看任务", "tone": "warning"})
            if failed_model_calls:
                cards.append({"id": "admin-model-failures", "eyebrow": "模型运行", "title": f"近 24 小时有 {failed_model_calls} 次模型请求失败",
                              "detail": "检查最近调用记录、错误类型和配置。", "button": "查看调用", "tone": "warning"})
            if inactive_users:
                cards.append({"id": "admin-inactive-users", "eyebrow": "用户治理", "title": f"{inactive_users} 个账号处于停用状态",
                              "detail": "核对账号状态，避免误停用影响教学。", "button": "查看用户", "tone": "neutral"})
            if not cards:
                cards.append({"id": "admin-overview", "eyebrow": "平台巡检", "title": "未发现上述待处理事项",
                              "detail": "可继续查看安全事件、模型用量与审计记录。", "button": "平台概览", "tone": "primary"})
            return cards

    def operations_report(self, days: int) -> dict:
        """Build an admin-only report from stored activity, not model-generated guesses."""
        generated_at = datetime.now(timezone.utc)
        since = generated_at - timedelta(days=days)
        with self._session_factory() as session:
            count = lambda statement: int(session.scalar(statement) or 0)
            published_courses = session.scalars(
                select(Course).where(Course.status == "published").order_by(Course.title)
            ).all()
            missing_materials = []
            for course in published_courses:
                ready_count = count(
                    select(func.count(Document.id))
                    .join(CourseKnowledgeBase, CourseKnowledgeBase.knowledge_base_id == Document.knowledge_base_id)
                    .where(CourseKnowledgeBase.course_id == course.id, Document.status == "ready",
                           Document.publication_status == "published")
                )
                if ready_count == 0:
                    missing_materials.append(course.title)
            metrics = {
                "total_users": count(select(func.count(User.id))),
                "inactive_users": count(select(func.count(User.id)).where(User.active.is_(False))),
                "published_courses": len(published_courses),
                "missing_material_courses": len(missing_materials),
                "ready_documents": count(select(func.count(Document.id)).where(
                    Document.status == "ready", Document.publication_status == "published")),
                "failed_jobs": count(select(func.count(DocumentIngestionJob.id)).where(
                    DocumentIngestionJob.status == "failed")),
                "period_rag_questions": count(select(func.count(QuestionRecord.id)).where(
                    QuestionRecord.created_at >= since)),
                "period_assignments": count(select(func.count(Assignment.id)).where(
                    Assignment.created_at >= since)),
                "period_model_calls": count(select(func.count(ModelUsageLog.id)).where(
                    ModelUsageLog.created_at >= since)),
                "period_model_failures": count(select(func.count(ModelUsageLog.id)).where(
                    ModelUsageLog.created_at >= since, ModelUsageLog.successful.is_(False),
                    ModelUsageLog.error_type.is_distinct_from("pending"),
                    ModelUsageLog.error_type.is_distinct_from("cancelled"))),
                "period_input_tokens": count(select(func.sum(ModelUsageLog.input_tokens)).where(
                    ModelUsageLog.created_at >= since)),
                "period_output_tokens": count(select(func.sum(ModelUsageLog.output_tokens)).where(
                    ModelUsageLog.created_at >= since)),
                "period_failed_logins": count(select(func.count(LoginAttempt.id)).where(
                    LoginAttempt.created_at >= since, LoginAttempt.successful.is_(False))),
                "period_rate_limited": count(select(func.count(RequestLog.id)).where(
                    RequestLog.created_at >= since, RequestLog.status_code == 429)),
                "period_server_errors": count(select(func.count(RequestLog.id)).where(
                    RequestLog.created_at >= since, RequestLog.status_code >= 500)),
            }
        checks = [
            {"id": "course_materials", "status": "warning" if missing_materials else "healthy",
             "title": "课程资料覆盖", "detail": (
                 f"{len(missing_materials)} 门已发布课程缺少可用资料：{'、'.join(missing_materials[:3])}。"
                 if missing_materials else f"{len(published_courses)} 门已发布课程均有可用资料。"),
             "action_id": "admin-course-materials"},
            {"id": "document_jobs", "status": "warning" if metrics["failed_jobs"] else "healthy",
             "title": "资料导入任务", "detail": f"当前有 {metrics['failed_jobs']} 个失败任务。",
             "action_id": "admin-jobs"},
            {"id": "model_calls", "status": "warning" if metrics["period_model_failures"] else "neutral" if not metrics["period_model_calls"] else "healthy",
             "title": "模型服务", "detail": (
                 f"本期调用 {metrics['period_model_calls']} 次，失败 {metrics['period_model_failures']} 次，"
                 f"估算 Token {metrics['period_input_tokens'] + metrics['period_output_tokens']}。"),
             "action_id": "admin-model-failures"},
            {"id": "security", "status": "warning" if any(metrics[key] for key in (
                "period_failed_logins", "period_rate_limited", "period_server_errors")) else "healthy",
             "title": "安全与运行", "detail": (
                 f"本期失败登录 {metrics['period_failed_logins']} 次、限流 {metrics['period_rate_limited']} 次、"
                 f"服务异常 {metrics['period_server_errors']} 次。"),
             "action_id": "admin-security"},
            {"id": "accounts", "status": "neutral", "title": "用户账号",
             "detail": f"共 {metrics['total_users']} 个账号，其中 {metrics['inactive_users']} 个已停用。",
             "action_id": "admin-inactive-users"},
        ]
        return {
            "period_days": days, "generated_at": generated_at, "period_start": since,
            "overall_status": "warning" if any(item["status"] == "warning" for item in checks) else "healthy",
            "metrics": metrics, "checks": checks,
        }

    def add_audit(self, *, actor_id: UUID | None, actor_name: str, action: str, resource_type: str, resource_id: str | None = None, detail: dict | None = None) -> None:
        with self._session_factory() as session:
            session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action=action, resource_type=resource_type, resource_id=resource_id, detail=detail or {}))
            session.commit()

    def list_audits(self, limit: int = 100, *, page: int | None = None, page_size: int = 10) -> list[dict] | dict:
        with self._session_factory() as session:
            query = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            def serialize(item):
                return {
                "id": str(item.id), "actor_name": item.actor_name, "action": item.action,
                "resource_type": item.resource_type, "resource_id": item.resource_id,
                "detail": item.detail, "created_at": item.created_at,
                }
            if page is not None:
                return sql_page(session, query, page=page, page_size=page_size, mapper=serialize)
            return [serialize(item) for item in session.scalars(query.limit(limit)).all()]

    @staticmethod
    def _user_dict(user: User) -> dict:
        return {
            "id": str(user.id), "username": user.username, "display_name": user.display_name,
            "role": user.role, "active": user.active, "created_at": user.created_at,
        }
