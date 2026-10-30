from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select

from app.models import AuditLog, ModelQuota, ModelUsageLog


def estimate_tokens(text: str) -> int:
    """Conservative estimate used when a compatible provider omits usage."""
    return max(1, (len(text.strip()) + 1) // 2) if text.strip() else 0


from app.pagination import sql_page


class ModelUsageService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def quotas(self) -> list[dict]:
        with self._session_factory() as session:
            return [{"role": row.role, "daily_limit": row.daily_limit} for row in session.scalars(
                select(ModelQuota).order_by(ModelQuota.role)).all()]

    def set_quota(self, role: str, daily_limit: int, *, actor_id: UUID | None,
                  actor_name: str, reason: str) -> dict:
        with self._session_factory() as session:
            result = self.set_quota_in_session(session, role, daily_limit, actor_id=actor_id,
                actor_name=actor_name, reason=reason)
            session.commit()
            return result

    @staticmethod
    def set_quota_in_session(session, role: str, daily_limit: int, *, actor_id: UUID | None,
                             actor_name: str, reason: str, operation_id: str | None = None) -> dict:
        explanation = reason.strip()
        if role not in {"student", "teacher", "admin"}:
            raise ValueError("角色无效。")
        if not 1 <= daily_limit <= 100000:
            raise ValueError("每日额度必须是 1 到 100000 的整数。")
        if len(explanation) < 5:
            raise ValueError("请填写至少 5 个字的额度修改原因。")
        item = session.scalar(select(ModelQuota).where(ModelQuota.role == role).with_for_update())
        if item is None:
            raise LookupError("角色配额不存在。")
        previous_limit = item.daily_limit
        if previous_limit == daily_limit:
            raise ValueError("每日额度未变化。")
        item.daily_limit = daily_limit
        session.add(AuditLog(
            actor_id=actor_id, actor_name=actor_name, action="update_quota",
            resource_type="model_quota", resource_id=role,
            detail={"previous_daily_limit": previous_limit, "daily_limit": daily_limit,
                    "reason": explanation, "confirmed": True,
                    **({"assistant_operation_id": operation_id} if operation_id else {})},
        ))
        return {"role": item.role, "daily_limit": item.daily_limit}

    def reserve(self, *, user_id: UUID, role: str, feature: str, provider: str, model: str) -> UUID | None:
        """Reserve one user operation under a locked quota; tool rounds share it."""
        with self._session_factory() as session:
            result = self.reserve_in_session(session, user_id=user_id, role=role,
                feature=feature, provider=provider, model=model)
            session.commit()
            return result

    @staticmethod
    def reserve_in_session(session, *, user_id: UUID, role: str, feature: str, provider: str, model: str) -> UUID | None:
        if provider == "offline":
            return None
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        quota = session.scalar(select(ModelQuota).where(ModelQuota.role == role).with_for_update())
        if quota is None:
            raise LookupError("角色配额尚未配置。")
        used = session.scalar(select(func.count(ModelUsageLog.id)).where(
            ModelUsageLog.user_id == user_id, ModelUsageLog.created_at >= day_start,
            ModelUsageLog.error_type.is_distinct_from("cancelled"))) or 0
        if used >= quota.daily_limit:
            raise PermissionError(f"今天的平台 AI 请求额度已用完（{quota.daily_limit} 次），请明天再试或联系管理员。")
        item = ModelUsageLog(user_id=user_id, role=role, feature=feature, provider=provider,
            model=model, input_tokens=0, output_tokens=0, duration_ms=0,
            successful=False, error_type="pending", created_at=datetime.now(timezone.utc))
        session.add(item)
        session.flush()
        return item.id

    def finish(self, reservation_id: UUID | None, *, input_text: str, output_text: str,
               duration_ms: float, successful: bool, error_type: str | None = None,
               token_counts: dict | None = None, usage_detail: dict | None = None) -> None:
        if reservation_id is None:
            return
        with self._session_factory() as session:
            self.finish_in_session(session, reservation_id, input_text=input_text, output_text=output_text,
                duration_ms=duration_ms, successful=successful, error_type=error_type,
                token_counts=token_counts, usage_detail=usage_detail)
            session.commit()

    @staticmethod
    def finish_in_session(session, reservation_id: UUID | None, *, input_text: str, output_text: str,
                          duration_ms: float, successful: bool, error_type: str | None = None,
                          token_counts: dict | None = None, usage_detail: dict | None = None) -> None:
        if reservation_id is None:
            return
        item = session.scalar(select(ModelUsageLog).where(ModelUsageLog.id == reservation_id).with_for_update())
        if item is None:
            raise LookupError('模型调用记录不存在。')
        # A late cancellation/failure callback must never rewrite a terminal settlement.
        if item.error_type != 'pending':
            return
        item.input_tokens = token_counts['input_tokens'] if token_counts is not None else estimate_tokens(input_text)
        item.output_tokens = token_counts['output_tokens'] if token_counts is not None else estimate_tokens(output_text)
        item.usage_detail = usage_detail
        item.duration_ms = round(duration_ms, 2)
        item.successful = successful
        item.error_type = error_type

    def record(self, *, user_id: UUID | None, role: str, feature: str, provider: str, model: str,
               input_text: str, output_text: str, duration_ms: float, successful: bool, error_type: str | None = None) -> None:
        with self._session_factory() as session:
            session.add(ModelUsageLog(user_id=user_id, role=role, feature=feature, provider=provider, model=model,
                input_tokens=estimate_tokens(input_text), output_tokens=estimate_tokens(output_text),
                duration_ms=round(duration_ms, 2), successful=successful, error_type=error_type))
            session.commit()

    def overview(self, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        with self._session_factory() as session:
            rows = list(session.scalars(select(ModelUsageLog).where(ModelUsageLog.created_at >= since).order_by(ModelUsageLog.created_at.desc())).all())
            total = len(rows); success = sum(1 for row in rows if row.successful)
            pending = sum(1 for row in rows if not row.successful and row.error_type == "pending")
            cancelled = sum(1 for row in rows if not row.successful and row.error_type == "cancelled")
            completed = [row for row in rows if row.successful or row.error_type not in {"pending", "cancelled"}]
            failed = len(completed) - success
            by_model: dict[str, dict] = {}
            for row in rows:
                item = by_model.setdefault(row.model, {"model": row.model, "calls": 0, "tokens": 0, "failures": 0})
                item["calls"] += 1; item["tokens"] += row.input_tokens + row.output_tokens
                item["failures"] += int(not row.successful and row.error_type not in {"pending", "cancelled"})
            return {"days": days, "total_calls": total, "successful_calls": success, "failed_calls": failed,
                "recorded_upstream_requests": sum((row.usage_detail or {}).get('upstream_requests', 0) for row in rows),
                "upstream_untracked_requests": sum(row.usage_detail is None for row in rows),
                "pending_calls": pending, "cancelled_calls": cancelled,
                "success_rate": round(success / len(completed) * 100, 1) if completed else 0.0,
                "input_tokens": sum(row.input_tokens for row in rows), "output_tokens": sum(row.output_tokens for row in rows),
                "average_duration_ms": round(sum(row.duration_ms for row in completed) / len(completed), 2) if completed else 0.0,
                "by_model": list(by_model.values()),
                "recent": [{"id": str(row.id), "role": row.role, "feature": row.feature, "model": row.model,
                    "tokens": row.input_tokens + row.output_tokens, "duration_ms": row.duration_ms,
                    "successful": row.successful, "error_type": row.error_type, "created_at": row.created_at,
                    "usage_detail": row.usage_detail} for row in rows[:30]]}

    def list_calls(self, *, page: int, page_size: int) -> dict:
        with self._session_factory() as session:
            return sql_page(session, select(ModelUsageLog).order_by(ModelUsageLog.created_at.desc(), ModelUsageLog.id.desc()),
                page=page, page_size=page_size, mapper=lambda row: {
                    "id": str(row.id), "role": row.role, "feature": row.feature, "model": row.model,
                    "tokens": row.input_tokens + row.output_tokens, "duration_ms": row.duration_ms,
                    "successful": row.successful, "error_type": row.error_type, "created_at": row.created_at,
                    "usage_detail": row.usage_detail})
