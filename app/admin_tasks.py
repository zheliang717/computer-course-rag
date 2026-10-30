"""Permission-scoped objects and explicit, durable administrator operation receipts."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import defer

from app.admin import AdminService
from app.generation import create_generator
from app.ingestion_jobs import DocumentIngestionService
from app.model_config import ModelConfigService
from app.model_usage import ModelUsageService
from app.models import AdminAssistantOperation, AuditLog, Document, DocumentIngestionJob, ModelQuota, ModelRuntimeConfig, ModelUsageLog, User
from app.pagination import sql_page


ROLE_LABELS = {"student": "学生", "teacher": "教师", "admin": "管理员"}


def utc(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class AdminTaskService:
    def __init__(self, session_factory, *, model_config_service=None, settings_provider=None):
        self._session_factory = session_factory
        self._model_config = model_config_service
        self._settings_provider = settings_provider

    @staticmethod
    def _actor(session, actor_id, *, lock=False):
        actor = session.scalar(select(User).where(User.id == actor_id).with_for_update()
            .execution_options(populate_existing=True)) if lock else session.get(User, actor_id)
        if not actor or not actor.active or actor.role != "admin":
            raise PermissionError("当前账号无权处理管理任务。")
        return actor

    @staticmethod
    def _record(row):
        state = row.status
        if state == "prepared" and utc(row.expires_at) <= datetime.now(timezone.utc):
            state = "expired"
        return {"id": str(row.id), "kind": row.kind, "target_id": row.target_id, "title": row.title,
            "reason": row.reason, "before": row.before, "proposed": row.proposed, "result": row.result,
            "status": state, "expires_at": row.expires_at, "created_at": row.created_at, "executed_at": row.executed_at}

    @staticmethod
    def _audit(session, actor, operation, action):
        session.add(AuditLog(actor_id=actor.id, actor_name=actor.display_name, action=action,
            resource_type="admin_assistant_operation", resource_id=str(operation.id),
            detail={"kind": operation.kind, "target_id": operation.target_id, "status": operation.status,
                "reason": operation.reason}))

    def _resource(self, session, kind, target_id, *, lock=False):
        if kind == "set_model_quota":
            if target_id not in ROLE_LABELS:
                raise ValueError("角色无效。")
            query = select(ModelQuota).where(ModelQuota.role == target_id)
            row = session.scalar(query.with_for_update() if lock else query)
            if not row:
                raise LookupError("角色额度不存在。")
            before = {"role": row.role, "daily_limit": row.daily_limit}
            version = utc(row.updated_at).isoformat()
        elif kind == "retry_document":
            try:
                job_id = UUID(target_id)
            except ValueError as exc:
                raise ValueError("资料任务标识无效。") from exc
            query = select(DocumentIngestionJob).where(DocumentIngestionJob.id == job_id)
            row = session.scalar(query.with_for_update() if lock else query)
            if not row:
                raise LookupError("资料任务不存在。")
            document = session.get(Document, row.document_id)
            before = {"title": document.filename if document else row.filename, "status": row.status,
                "attempts": row.attempts, "has_source_file": bool(row.source_payload), "error_message": row.error_message}
            version = {"payload_hash": hashlib.sha256(row.source_payload or b"").hexdigest(),
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None}
        elif kind in {"set_user_active", "set_user_role"}:
            try:
                user_id = UUID(target_id)
            except ValueError as exc:
                raise ValueError("账号标识无效。") from exc
            row, count = AdminService.governance_target(session, user_id, lock=lock)
            if row is None:
                raise LookupError("账号不存在。")
            before = {key: getattr(row, key) for key in ("username", "display_name", "role", "active")}
            version = {"active_admins": sorted(str(item) for item in session.scalars(select(User.id).where(
                User.role == "admin", User.active.is_(True)))), "created_at": row.created_at.isoformat()}
        elif kind == "set_model_config":
            if target_id != "current" or self._model_config is None or self._settings_provider is None:
                raise ValueError("当前模型配置不可用，请刷新管理设置。")
            query = select(ModelRuntimeConfig).where(ModelRuntimeConfig.id == 1)
            row = session.scalar(query.with_for_update() if lock else query)
            effective = self._model_config.load_in_session(session, self._settings_provider(), allow_credential_failure=True)
            before = self._model_config.public_values(effective)
            version = {"updated_at": row.updated_at.isoformat() if row else None,
                "credential_fingerprint": hashlib.sha256((row.api_key_ciphertext if row and row.api_key_ciphertext else effective.llm_api_key or "").encode()).hexdigest()}
        else:
            raise ValueError("不支持的管理操作。")
        signature = hashlib.sha256(json.dumps({"kind": kind, "target_id": target_id,
            "before": before, "version": version}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return before, signature

    def users(self, *, page, page_size, keyword="", role="all", active="all"):
        with self._session_factory() as session:
            query = select(User.id, User.username, User.display_name, User.role, User.active, User.created_at)
            if keyword.strip():
                query = query.where(or_(User.username.ilike(f"%{keyword.strip()}%"), User.display_name.ilike(f"%{keyword.strip()}%")))
            if role != "all":
                query = query.where(User.role == role)
            if active != "all":
                query = query.where(User.active.is_(active == "active"))
            if keyword.strip():
                query = query.order_by(case((User.username == keyword.strip(), 0), (User.display_name == keyword.strip(), 1), else_=2))
            return sql_page(session, query.order_by(User.created_at.desc(), User.id.desc()), page=page, page_size=page_size,
                scalar=False, mapper=lambda row: {"id": str(row.id), "username": row.username,
                    "display_name": row.display_name, "role": row.role, "active": row.active, "created_at": row.created_at})

    def user(self, user_id, *, actor_id):
        with self._session_factory() as session:
            self._actor(session, actor_id)
            target, count = AdminService.governance_target(session, user_id, lock=False)
            if target is None:
                raise LookupError("账号不存在。")
            return {**AdminService._user_dict(target), "is_current_actor": target.id == actor_id,
                "is_last_active_admin": target.role == "admin" and target.active and count <= 1}

    def model(self):
        if self._model_config is None or self._settings_provider is None:
            raise ValueError("模型配置暂不可用。")
        with self._session_factory() as session:
            runtime = self._settings_provider()
            effective = self._model_config.load_in_session(session, runtime, allow_credential_failure=True)
            row = session.get(ModelRuntimeConfig, 1)
            return {**self._model_config.public_values(effective),
                "credential_recovery_required": bool(row and row.api_key_ciphertext and not effective.llm_api_key),
                "runtime_synchronized": self._model_config.same_settings(effective, runtime),
                "updated_at": row.updated_at if row else None}

    def jobs(self, *, page, page_size, status="failed", keyword=""):
        with self._session_factory() as session:
            query = select(DocumentIngestionJob, Document.filename,
                func.octet_length(DocumentIngestionJob.source_payload) > 0).options(
                    defer(DocumentIngestionJob.source_payload)).join(Document, Document.id == DocumentIngestionJob.document_id)
            if status != "all":
                query = query.where(DocumentIngestionJob.status == status)
            if keyword.strip():
                query = query.where(or_(Document.filename.ilike(f"%{keyword.strip()}%"),
                    DocumentIngestionJob.filename.ilike(f"%{keyword.strip()}%")))
            return sql_page(session, query.order_by(DocumentIngestionJob.created_at.desc(), DocumentIngestionJob.id.desc()),
                page=page, page_size=page_size, scalar=False, mapper=lambda row: {
                    **DocumentIngestionService._dict(row[0]), "document_title": row[1], "has_source_file": bool(row[2])})

    def quotas(self):
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        with self._session_factory() as session:
            used = dict(session.execute(select(ModelUsageLog.role, func.count(ModelUsageLog.id)).where(
                ModelUsageLog.created_at >= start, ModelUsageLog.error_type.is_distinct_from("cancelled"))
                .group_by(ModelUsageLog.role)).all())
            return [{"role": row.role, "role_label": ROLE_LABELS[row.role], "daily_limit": row.daily_limit,
                "used_today": used.get(row.role, 0),
                "resets_at": start + timedelta(days=1)} for row in session.scalars(select(ModelQuota).order_by(ModelQuota.role))]

    def calls(self, *, page, page_size, days=7):
        with self._session_factory() as session:
            query = select(ModelUsageLog, User.display_name).outerjoin(User, User.id == ModelUsageLog.user_id).where(
                ModelUsageLog.created_at >= datetime.now(timezone.utc) - timedelta(days=days),
                ModelUsageLog.successful.is_(False), ModelUsageLog.error_type.is_distinct_from("pending"),
                ModelUsageLog.error_type.is_distinct_from("cancelled"))
            return sql_page(session, query.order_by(ModelUsageLog.created_at.desc(), ModelUsageLog.id.desc()),
                page=page, page_size=page_size, scalar=False, mapper=lambda row: {
                    "id": str(row[0].id), "role": row[0].role, "user_name": row[1] or "已删除账号",
                    "model": row[0].model, "feature": row[0].feature, "error_type": row[0].error_type or "未分类错误",
                    "duration_ms": row[0].duration_ms, "created_at": row[0].created_at})

    def operations(self, *, actor_id, page, page_size):
        with self._session_factory() as session:
            self._actor(session, actor_id)
            return sql_page(session, select(AdminAssistantOperation).where(AdminAssistantOperation.actor_id == actor_id)
                .order_by(AdminAssistantOperation.created_at.desc(), AdminAssistantOperation.id.desc()),
                page=page, page_size=page_size, mapper=self._record)

    def get(self, operation_id, *, actor_id):
        with self._session_factory() as session:
            self._actor(session, actor_id)
            row = session.get(AdminAssistantOperation, operation_id)
            if not row or row.actor_id != actor_id:
                raise LookupError("操作记录不存在或不是本人创建的预览。")
            return self._record(row)

    def prepare(self, *, actor_id, kind, target_id, reason, daily_limit=None, active=None, role=None, config=None):
        explanation = reason.strip()
        if not 5 <= len(explanation) <= 500:
            raise ValueError("请填写至少 5 个字的操作原因。")
        with self._session_factory() as session:
            actor = self._actor(session, actor_id)
            allowed = {"set_model_quota": "daily_limit", "set_user_active": "active", "set_user_role": "role", "set_model_config": "config"}.get(kind)
            if any(value is not None and name != allowed for name, value in {
                "daily_limit": daily_limit, "active": active, "role": role, "config": config}.items()):
                raise ValueError("操作参数与所选类型不一致，未创建预览。")
            before, signature = self._resource(session, kind, target_id)
            private = {}
            if kind == "set_model_quota":
                if daily_limit is None or not 1 <= daily_limit <= 100000:
                    raise ValueError("每日额度必须是 1 到 100000 的整数。")
                if daily_limit == before["daily_limit"]:
                    raise ValueError("每日额度未变化，无需创建操作预览。")
                proposed = {"role": target_id, "daily_limit": daily_limit}
                title = f"调整{ROLE_LABELS[target_id]}模型额度"
            elif kind in {"set_user_active", "set_user_role"}:
                target, count = AdminService.governance_target(session, UUID(target_id), lock=False)
                if kind == "set_user_active":
                    if active is None or active == target.active:
                        raise ValueError("请指定不同的账号状态。")
                    AdminService.validate_user_change(target, count, active=active, actor_id=actor_id)
                    proposed, title = {"active": active}, f"{'启用' if active else '停用'}账号：{target.display_name}"
                else:
                    if role is None:
                        raise ValueError("请选择目标角色。")
                    AdminService.validate_user_change(target, count, role=role, actor_id=actor_id)
                    proposed, title = {"role": role}, f"调整账号角色：{target.display_name}"
            elif kind == "set_model_config":
                if config is None:
                    raise ValueError("请填写模型配置。")
                baseline = self._model_config.load_in_session(session, self._settings_provider(), allow_credential_failure=True)
                candidate = self._model_config.candidate(baseline, config)
                create_generator(candidate)  # Validate provider construction without a network call.
                if self._model_config.same_settings(candidate, baseline):
                    raise ValueError("模型设置没有变化，无需创建预览。")
                new_key = config.get("api_key")
                if new_key and new_key.strip():
                    private["api_key_ciphertext"] = self._model_config.encrypt_key(new_key)
                proposed = {**self._model_config.public_values(candidate), "api_key_changed": bool(private)}
                title = "调整生成模型与 RAG 配置"
            else:
                if before["status"] != "failed" or not before["has_source_file"]:
                    raise ValueError("只有原始文件仍可用的失败任务可以重试。")
                proposed = {"status": "queued", "progress_percent": 0}
                title = f"重新处理：{before['title']}"[:500]
            row = AdminAssistantOperation(actor_id=actor_id, kind=kind, target_id=target_id, title=title,
                reason=explanation, expected_signature=signature, before=before, proposed=proposed,
                private_payload=private, status="prepared", expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
            session.add(row)
            session.flush()
            self._audit(session, actor, row, "prepare_admin_action")
            session.commit()
            return self._record(row)

    def resolve(self, operation_id, *, actor_id, execute=False, confirmed=False):
        if execute and not confirmed:
            raise ValueError("请核对预览并明确确认，尚未执行操作。")
        with self._session_factory() as session:
            actor = self._actor(session, actor_id)
            row = session.scalar(select(AdminAssistantOperation).where(
                AdminAssistantOperation.id == operation_id, AdminAssistantOperation.actor_id == actor_id).with_for_update())
            if row is None:
                raise LookupError("操作记录不存在或不是本人创建的预览。")
            if row.status != "prepared":
                self._actor(session, actor_id, lock=True)
                return self._record(row), False
            now = datetime.now(timezone.utc)
            if utc(row.expires_at) <= now:
                self._actor(session, actor_id, lock=True)
                row.status, row.result = "expired", {"message": "预览已过期，没有执行变更。"}
            elif not execute:
                self._actor(session, actor_id, lock=True)
                row.status, row.result = "cancelled", {"message": "已取消，没有修改目标对象。"}
            else:
                try:
                    _, signature = self._resource(session, row.kind, row.target_id, lock=True)
                except LookupError:
                    signature = None
                actor = self._actor(session, actor_id, lock=True)
                if signature != row.expected_signature:
                    row.status, row.result = "stale", {"message": "目标已变化或被移除，没有执行旧操作，请刷新后重新预览。"}
                else:
                    if row.kind == "set_model_quota":
                        result = ModelUsageService.set_quota_in_session(session, row.target_id, row.proposed["daily_limit"],
                            actor_id=actor_id, actor_name=actor.display_name, reason=row.reason, operation_id=str(row.id))
                        message = "额度已更新，结果已保存。"
                    elif row.kind == "set_user_active":
                        result = AdminService.set_user_active_in_session(session, UUID(row.target_id), row.proposed["active"],
                            actor_id=actor_id, actor_name=actor.display_name, confirmed=True, reason=row.reason, operation_id=str(row.id))
                        message = "账号状态已更新；已有登录将在后续请求按新状态鉴权。"
                    elif row.kind == "set_user_role":
                        result = AdminService.set_user_role_in_session(session, UUID(row.target_id), row.proposed["role"],
                            actor_id=actor_id, actor_name=actor.display_name, reason=row.reason, operation_id=str(row.id))
                        message = "账号角色已更新，后续请求按新角色鉴权。"
                    elif row.kind == "set_model_config":
                        baseline = self._model_config.load_in_session(session, self._settings_provider(), allow_credential_failure=True)
                        values = {key: value for key, value in row.proposed.items() if key not in {"configured", "api_key_changed"}}
                        ciphertext = row.private_payload.get("api_key_ciphertext")
                        if ciphertext:
                            values["api_key"] = self._model_config.decrypt_key(ciphertext)
                        candidate = self._model_config.candidate(baseline, values)
                        create_generator(candidate)
                        self._model_config.save_in_session(session, candidate, ciphertext=ciphertext, actor_id=actor_id,
                            actor_name=actor.display_name, reason=row.reason, operation_id=str(row.id))
                        result = self._model_config.public_values(candidate)
                        message = "配置已保存；运行态同步结果以本次响应及当前配置状态为准。"
                    else:
                        result = DocumentIngestionService.retry_in_session(session, UUID(row.target_id), actor_id=actor_id,
                            actor_name=actor.display_name, reason=row.reason, confirmed=True, operation_id=str(row.id))
                        message = "任务已重新排队，处理结果请刷新任务详情查看。"
                    safe_result = {key: value.isoformat() if isinstance(value, datetime) else value for key, value in result.items()}
                    row.status, row.result, row.executed_at = "applied", {"message": message, "object": safe_result}, now
            row.private_payload = {}
            self._audit(session, actor, row, "resolve_admin_action")
            session.commit()
            return self._record(row), execute and row.status == "applied" and row.kind == "retry_document"

    def answer(self, *, question):
        compact = re.sub(r"\s+", "", question)
        if re.search(r"(?:模型|调用).*(?:额度|配额)|(?:额度|配额).*(?:调整|修改|查看|剩余)|(?:学生|教师|管理员)额度", compact):
            quotas = self.quotas()
            lines = ["### 模型额度", "", *[f"- {item['role_label']}：每人每日上限 {item['daily_limit']} 次；该角色今日累计调用 {item['used_today']} 次。" for item in quotas],
                "", "打开具体角色后填写额度和原因，核对预览后再确认执行。当前只查询记录，没有修改额度。"]
            role = next((key for key, label in ROLE_LABELS.items() if label in compact), None)
            target, title = f"quota:{role}" if role else "quotas", "查看额度并准备操作"
        elif re.search(r"导入失败|失败.*(?:资料|导入|任务)|(?:资料|导入).*失败|重试.*(?:资料|任务)", compact):
            failed = self.jobs(page=1, page_size=1)
            lines = ["### 资料处理任务", "", f"当前有 **{failed['total']}** 个失败任务。", "",
                "可打开具体任务查看原因与原始文件是否可用，再预览、确认重试。未执行任何重试。"]
            target, title = "jobs", "查看资料任务"
        elif re.search(r"(?:模型|接口|调用).*(?:失败|异常|故障)|(?:失败|异常).*(?:模型|调用)", compact):
            failed = self.calls(page=1, page_size=1)
            lines = ["### 模型异常记录", "", f"近 7 天有 **{failed['total']}** 条已结束的失败调用记录。", "",
                "可核对具体错误类型、功能与发生时间，再查看模型配置或角色额度；不会自动重放原提问或调整设置。"]
            target, title = "calls", "查看具体模型异常"
        elif re.search(r"模型配置|模型设置|切换模型|模型参数|检索参数|RAG参数|请求超时", compact, re.IGNORECASE):
            current = self.model()
            lines = ["### 当前模型配置", "", f"已保存模型：**{current['model']}**；请求超时 {current['timeout_seconds']:g} 秒。", "",
                "打开配置对象后修改并核对前后差异，再明确确认。当前只是读取配置，没有更换模型、密钥或检索参数，也没有探测外部服务。"]
            target, title = "model", "查看并准备模型配置变更"
        elif re.search(r"账号|用户.*(?:状态|角色|权限)|角色.*(?:调整|修改)|(?:停用|启用).*用户", compact):
            target = "accounts"
            name = re.search(r"(?:账号|学号|用户名)\s*([A-Za-z0-9_-]{3,80})", question)
            if name:
                with self._session_factory() as session:
                    user_id = session.scalar(select(User.id).where(User.username == name.group(1)))
                if user_id:
                    target = f"user:{user_id}"
            lines = ["### 账号治理", "", "可按姓名、登录账号、角色或启用状态找到具体用户，准备启停或角色变更并核对影响。", "",
                "不会修改自己的角色或停用最后一名启用管理员；当前没有修改任何账号，也不会读取或显示密码。"]
            title = "打开具体账号" if target.startswith("user:") else "查找账号并准备处理"
        elif re.search(r"操作记录|处理记录|执行结果|管理任务", compact):
            lines = ["### 管理任务", "", "可查看本人操作预览、取消与执行结果；有效预览须明确确认后才执行。"]
            target, title = "history", "查看我的处理记录"
        else:
            return None
        return {"answer": "\n".join(lines), "message": "根据当前管理记录查询；没有由模型自行执行管理操作。",
            "actions": [{"kind": "admin_tasks", "target_id": target, "title": title,
                "detail": "查看具体对象；所有实际变更须先预览并明确确认。"}]}
