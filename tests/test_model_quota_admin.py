"""Changing a model quota requires an admin decision and atomic audit."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.auth import AuthService, Principal
from app.database import Base
from app.model_usage import ModelUsageService
from app.models import AuditLog, ModelQuota, User


def test_model_quota_confirmation_permissions_and_audit_rollback(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    admin_id, teacher_id, student_id = (uuid4() for _ in range(3))
    with sessions.begin() as session:
        session.add_all([
            User(id=admin_id, username="quota_admin", display_name="额度管理员", role="admin", active=True, password_hash="x"),
            User(id=teacher_id, username="quota_teacher", display_name="额度教师", role="teacher", active=True, password_hash="x"),
            User(id=student_id, username="quota_student", display_name="额度学生", role="student", active=True, password_hash="x"),
            ModelQuota(role="student", daily_limit=10),
        ])
    auth = AuthService(sessions, secret="quota-test-secret", required=True)
    monkeypatch.setattr(main_module, "auth", auth)
    monkeypatch.setattr(main_module, "model_usage", ModelUsageService(sessions))
    client = TestClient(main_module.app)

    def headers(user_id, username, role):
        principal = Principal(id=str(user_id), username=username, display_name=username, role=role)
        return {"Authorization": "Bearer " + auth.issue_token(principal)}

    admin = headers(admin_id, "quota_admin", "admin")
    teacher = headers(teacher_id, "quota_teacher", "teacher")
    student = headers(student_id, "quota_student", "student")
    path = "/api/v1/admin/model-quotas/student"
    body = {"daily_limit": 20, "reason": "课程试用期间调整额度", "confirmed": True}
    assert client.put(path, headers=student, json=body).status_code == 403
    assert client.put(path, headers=teacher, json=body).status_code == 403
    assert client.put(path, headers=admin, json={**body, "confirmed": False}).status_code == 409
    assert client.put(path, headers=admin, json={**body, "reason": "短"}).status_code == 409
    assert client.put(path, headers=admin, json={**body, "daily_limit": 100001}).status_code == 422
    with sessions() as session:
        assert session.get(ModelQuota, "student").daily_limit == 10
        assert list(session.scalars(select(AuditLog)).all()) == []

    changed = client.put(path, headers=admin, json=body)
    assert changed.status_code == 200, changed.text
    assert changed.json() == {"role": "student", "daily_limit": 20}
    assert client.put(path, headers=admin, json=body).status_code == 409
    with sessions() as session:
        audit = session.scalar(select(AuditLog))
        assert audit is not None and audit.actor_id == admin_id
        assert audit.action == "update_quota" and audit.resource_id == "student"
        assert audit.detail == {"previous_daily_limit": 10, "daily_limit": 20,
                                "reason": body["reason"], "confirmed": True}

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit storage failed")

    event.listen(AuditLog, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit storage failed"):
            client.put(path, headers=admin, json={**body, "daily_limit": 30})
    finally:
        event.remove(AuditLog, "before_insert", fail_audit)
    with sessions() as session:
        assert session.get(ModelQuota, "student").daily_limit == 20
        assert len(list(session.scalars(select(AuditLog)).all())) == 1
