"""The operational report is structured and only available to administrators."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import main as main_module


client = TestClient(main_module.app)


def _headers(username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_report_scope_and_period_validation(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    calls: list[int] = []

    class FakeReportService:
        def operations_report(self, days: int) -> dict:
            calls.append(days)
            return {
                "period_days": days, "generated_at": now,
                "period_start": now - timedelta(days=days), "overall_status": "warning",
                "metrics": {"published_courses": 2, "failed_jobs": 1},
                "checks": [{"id": "document_jobs", "status": "warning", "title": "资料导入任务",
                            "detail": "当前有 1 个失败任务。", "action_id": "admin-jobs"}],
            }

    monkeypatch.setattr(main_module, "admin_service", FakeReportService())
    admin = _headers("admin", "admin123")
    student = _headers("student", "student123")

    denied = client.get("/api/v1/admin/operations-report?days=7", headers=student)
    assert denied.status_code == 403
    invalid = client.get("/api/v1/admin/operations-report?days=2", headers=admin)
    assert invalid.status_code == 422
    assert calls == []

    report = client.get("/api/v1/admin/operations-report?days=7", headers=admin)
    assert report.status_code == 200
    assert report.json()["period_days"] == 7
    assert report.json()["checks"][0]["action_id"] == "admin-jobs"
    assert calls == [7]
