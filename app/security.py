from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic

from sqlalchemy import delete, func, select

from app.models import LoginAttempt, RequestLog


class SlidingWindowRateLimiter:
    """Thread-safe single-node limiter with endpoint-specific sliding windows."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: int = 60) -> tuple[bool, int, int]:
        now = monotonic()
        threshold = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= threshold:
                events.popleft()
            if len(events) >= limit:
                retry_after = min(window_seconds, max(1, int(window_seconds - (now - events[0])) + 1))
                return False, 0, retry_after
            events.append(now)
            return True, max(0, limit - len(events)), 0


from app.pagination import sql_page


class SecurityService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def is_login_blocked(self, username: str, ip_address: str, *, limit: int = 5, minutes: int = 15) -> bool:
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        with self._session_factory() as session:
            failures = session.scalar(select(func.count(LoginAttempt.id)).where(
                LoginAttempt.username == username.strip().lower(),
                LoginAttempt.ip_address == ip_address,
                LoginAttempt.successful.is_(False),
                LoginAttempt.created_at >= since,
            ))
            return int(failures or 0) >= limit

    def record_login(self, username: str, ip_address: str, *, successful: bool) -> None:
        normalized = username.strip().lower()
        with self._session_factory() as session:
            if successful:
                session.execute(delete(LoginAttempt).where(
                    LoginAttempt.username == normalized,
                    LoginAttempt.ip_address == ip_address,
                    LoginAttempt.successful.is_(False),
                ))
            session.add(LoginAttempt(username=normalized, ip_address=ip_address, successful=successful))
            session.commit()

    def record_request(self, *, request_id: str, method: str, path: str, status_code: int, duration_ms: float, ip_address: str) -> None:
        with self._session_factory() as session:
            session.add(RequestLog(
                request_id=request_id, method=method[:10], path=path[:500], status_code=status_code,
                duration_ms=round(duration_ms, 2), ip_address=ip_address[:80],
            ))
            session.commit()

    def overview(self, *, limit: int = 50) -> dict:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        with self._session_factory() as session:
            failed = int(session.scalar(select(func.count(LoginAttempt.id)).where(
                LoginAttempt.successful.is_(False), LoginAttempt.created_at >= since,
            )) or 0)
            limited = int(session.scalar(select(func.count(RequestLog.id)).where(
                RequestLog.status_code == 429, RequestLog.created_at >= since,
            )) or 0)
            errors = int(session.scalar(select(func.count(RequestLog.id)).where(
                RequestLog.status_code >= 500, RequestLog.created_at >= since,
            )) or 0)
            average = float(session.scalar(select(func.avg(RequestLog.duration_ms)).where(
                RequestLog.created_at >= since,
            )) or 0.0)
            attempts = session.scalars(select(LoginAttempt).order_by(LoginAttempt.created_at.desc()).limit(limit)).all()
            requests = session.scalars(select(RequestLog).order_by(RequestLog.created_at.desc()).limit(limit)).all()
            return {
                "failed_logins_24h": failed, "rate_limited_requests_24h": limited,
                "server_errors_24h": errors, "average_duration_ms_24h": round(average, 2),
                "login_attempts": [{
                    "id": str(item.id), "username": item.username, "ip_address": item.ip_address,
                    "successful": item.successful, "created_at": item.created_at,
                } for item in attempts],
                "request_logs": [{
                    "id": str(item.id), "request_id": item.request_id, "method": item.method,
                    "path": item.path, "status_code": item.status_code, "duration_ms": item.duration_ms,
                    "ip_address": item.ip_address, "created_at": item.created_at,
                } for item in requests],
            }

    def list_events(self, *, kind: str, page: int, page_size: int) -> dict:
        model = LoginAttempt if kind == "logins" else RequestLog
        fields = ("username", "ip_address", "successful", "created_at") if kind == "logins" else (
            "request_id", "method", "path", "status_code", "duration_ms", "ip_address", "created_at")
        with self._session_factory() as session:
            return sql_page(session, select(model).order_by(model.created_at.desc(), model.id.desc()),
                            page=page, page_size=page_size,
                            mapper=lambda item: {"id": str(item.id), **{field: getattr(item, field) for field in fields}})
