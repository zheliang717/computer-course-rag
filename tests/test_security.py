from app.security import SlidingWindowRateLimiter

from fastapi.testclient import TestClient

from app import main as main_module
from app.auth import AuthService, Principal


def test_sliding_window_rate_limiter_reports_remaining_and_retry() -> None:
    limiter = SlidingWindowRateLimiter()
    assert limiter.check("client:ai", limit=2, window_seconds=60) == (True, 1, 0)
    assert limiter.check("client:ai", limit=2, window_seconds=60) == (True, 0, 0)
    allowed, remaining, retry_after = limiter.check("client:ai", limit=2, window_seconds=60)
    assert allowed is False
    assert remaining == 0
    assert 1 <= retry_after <= 60


def test_authenticated_users_do_not_share_proxy_rate_limit(monkeypatch) -> None:
    auth = AuthService(None, secret="rate-limit-test", required=False)

    class RecordingLimiter:
        keys = []

        def check(self, key, *, limit):
            self.keys.append((key, limit))
            return True, limit - 1, 0

    limiter = RecordingLimiter()
    monkeypatch.setattr(main_module, "auth", auth)
    monkeypatch.setattr(main_module, "rate_limiter", limiter)
    client = TestClient(main_module.app)
    for user_id in ("student-one", "teacher-two"):
        token = auth.issue_token(Principal(id=user_id, username=user_id, display_name=user_id, role="student"))
        assert client.get("/health", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/health", headers={"Authorization": "Bearer invalid"}).status_code == 200
    assert limiter.keys[0] == ("user:student-one:api-read", 300)
    assert limiter.keys[1] == ("user:teacher-two:api-read", 300)
    assert limiter.keys[2][0].startswith("ip:")


def test_read_and_write_requests_have_separate_limits() -> None:
    assert main_module._request_limit("/api/v1/courses", "GET") == ("api-read", 300)
    assert main_module._request_limit("/api/v1/courses", "POST") == ("api-write", 120)
    assert main_module._request_limit("/api/v1/questions/ask", "POST") == ("ai", 30)
    assert main_module._request_limit("/api/v1/auth/login", "POST") == ("login", 20)
