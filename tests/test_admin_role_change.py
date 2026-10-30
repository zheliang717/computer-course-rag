"""Role changes require confirmation and commit with an audit record."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.admin import AdminService
from app.auth import AuthService, Principal
from app.database import Base
from app.models import AuditLog, User


def test_role_change_permissions_audit_and_existing_session_refresh(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    admin_id, other_admin_id, student_id = (uuid4() for _ in range(3))
    with sessions.begin() as session:
        session.add_all([
            User(id=admin_id, username="role_admin", display_name="管理员甲", role="admin", active=True, password_hash="x"),
            User(id=other_admin_id, username="role_other", display_name="管理员乙", role="admin", active=True, password_hash="x"),
            User(id=student_id, username="role_student", display_name="学生甲", role="student", active=True, password_hash="x"),
        ])
    auth = AuthService(sessions, secret="role-test-secret", required=True)
    service = AdminService(sessions)
    monkeypatch.setattr(main_module, "auth", auth)
    monkeypatch.setattr(main_module, "admin_service", service)
    client = TestClient(main_module.app)
    admin = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(admin_id), username="role_admin", display_name="管理员甲", role="admin"))}
    student = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(student_id), username="role_student", display_name="学生甲", role="student"))}
    path = f"/api/v1/admin/users/{student_id}/role"
    body = {"role": "teacher", "reason": "经课程负责人确认需要授课"}
    assert client.patch(path, headers=admin, json=body).status_code == 409
    assert client.patch(path, headers=student, json={**body, "confirmed": True}).status_code == 403
    assert client.patch(f"/api/v1/admin/users/{admin_id}/role", headers=admin,
                        json={**body, "confirmed": True}).status_code == 409
    with sessions() as session:
        assert session.get(User, student_id).role == "student"
        assert list(session.scalars(select(AuditLog)).all()) == []

    changed = client.patch(path, headers=admin, json={**body, "confirmed": True})
    assert changed.status_code == 200, changed.text
    assert changed.json()["role"] == "teacher"
    assert client.get("/api/v1/auth/me", headers=student).json()["role"] == "teacher"
    with sessions() as session:
        audits = list(session.scalars(select(AuditLog)).all())
        assert len(audits) == 1 and audits[0].action == "change_role"
        assert audits[0].detail == {"username": "role_student", "from_role": "student",
                                    "to_role": "teacher", "reason": body["reason"], "confirmed": True}
    assert client.patch(path, headers=admin, json={**body, "confirmed": True}).status_code == 409

    service.set_user_role(other_admin_id, "teacher", actor_id=admin_id,
                          actor_name="管理员甲", reason="调整管理员职责至授课岗位")
    with pytest.raises(ValueError, match="最后一名"):
        service.set_user_role(admin_id, "teacher", actor_id=uuid4(),
                              actor_name="另一管理员", reason="不应移除最后管理员")

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit storage failed")

    event.listen(AuditLog, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit storage failed"):
            service.set_user_role(student_id, "admin", actor_id=admin_id,
                                  actor_name="管理员甲", reason="测试审计失败回滚")
    finally:
        event.remove(AuditLog, "before_insert", fail_audit)
    with sessions() as session:
        assert session.get(User, student_id).role == "teacher"

    create_payload = {"username": "new_admin", "display_name": "新管理员",
                      "role": "admin", "password": "SecurePass123!"}
    assert client.post("/api/v1/admin/users", headers=admin, json=create_payload).status_code == 409
    with sessions() as session:
        assert session.scalar(select(User).where(User.username == "new_admin")) is None
    created = client.post("/api/v1/admin/users", headers=admin,
                          json={**create_payload, "confirmed": True})
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "admin"
    with sessions() as session:
        creation = session.scalar(select(AuditLog).where(AuditLog.resource_id == created.json()["id"]))
        assert creation is not None and creation.action == "create"
        assert creation.detail["confirmed"] is True

    event.listen(AuditLog, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit storage failed"):
            service.create_user(username="unlogged_admin", display_name="不应创建", role="admin",
                                password="SecurePass123!", actor_id=admin_id,
                                actor_name="管理员甲", confirmed=True)
    finally:
        event.remove(AuditLog, "before_insert", fail_audit)
    with sessions() as session:
        assert session.scalar(select(User).where(User.username == "unlogged_admin")) is None

    event.listen(AuditLog, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit storage failed"):
            service.set_user_active(student_id, False, actor_id=admin_id,
                                    actor_name="管理员甲", confirmed=True)
    finally:
        event.remove(AuditLog, "before_insert", fail_audit)
    with sessions() as session:
        assert session.get(User, student_id).active is True
