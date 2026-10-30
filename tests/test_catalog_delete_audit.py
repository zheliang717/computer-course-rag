"""Destructive catalog operations and their audit records share a transaction."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.auth import AuthService, Principal
from app.catalog import KnowledgeCatalog
from app.database import Base
from app.models import AuditLog, Document, KnowledgeBase, User


def _catalog_database():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    actor_id, base_id, other_base_id, document_id = (uuid4() for _ in range(4))
    with sessions.begin() as session:
        session.add(User(id=actor_id, username="audit_admin", display_name="审计管理员",
                         role="admin", active=True, password_hash="x"))
        session.add_all([
            KnowledgeBase(id=base_id, name="删除审计资料库", course="数据结构"),
            KnowledgeBase(id=other_base_id, name="其他资料库", course="操作系统"),
        ])
        session.add(Document(id=document_id, knowledge_base_id=base_id, filename="测试讲义.pdf"))
    return sessions, actor_id, base_id, other_base_id, document_id


def test_document_delete_requires_confirmation_and_commits_audit(monkeypatch) -> None:
    sessions, actor_id, base_id, _other_base_id, document_id = _catalog_database()
    service = KnowledgeCatalog(sessions)
    auth = AuthService(sessions, secret="catalog-audit-secret", required=True)
    monkeypatch.setattr(main_module, "catalog", service)
    monkeypatch.setattr(main_module, "auth", auth)
    token = auth.issue_token(Principal(id=str(actor_id), username="audit_admin",
                                       display_name="审计管理员", role="admin"))
    client = TestClient(main_module.app)
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/api/v1/documents/{document_id}"
    assert client.delete(path, headers=headers).status_code == 409
    with sessions() as session:
        assert session.get(Document, document_id) is not None
        assert list(session.scalars(select(AuditLog)).all()) == []

    result = client.delete(path, headers={**headers, "X-Confirm-Action": "true"})
    assert result.status_code == 204, result.text
    with sessions() as session:
        assert session.get(Document, document_id) is None
        audit = session.scalar(select(AuditLog))
        assert audit is not None
        assert audit.resource_type == "document" and audit.resource_id == str(document_id)
        assert audit.detail == {"knowledge_base_id": str(base_id),
                                "filename": "测试讲义.pdf", "confirmed": True}


def test_document_and_knowledge_base_remain_if_audit_write_fails() -> None:
    sessions, actor_id, base_id, other_base_id, document_id = _catalog_database()
    service = KnowledgeCatalog(sessions)

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit storage failed")

    event.listen(AuditLog, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit storage failed"):
            service.delete_document(document_id, expected_knowledge_base_id=base_id,
                                    actor_id=actor_id, actor_name="审计管理员")
        with pytest.raises(RuntimeError, match="audit storage failed"):
            service.delete_knowledge_base(base_id, actor_id=actor_id, actor_name="审计管理员")
    finally:
        event.remove(AuditLog, "before_insert", fail_audit)
    with sessions() as session:
        assert session.get(Document, document_id) is not None
        assert session.get(KnowledgeBase, base_id) is not None
        assert list(session.scalars(select(AuditLog)).all()) == []

    assert service.delete_document(document_id, expected_knowledge_base_id=other_base_id,
                                   actor_id=actor_id, actor_name="审计管理员") is False
    assert service.delete_knowledge_base(base_id, actor_id=actor_id, actor_name="审计管理员") is True
    with sessions() as session:
        assert session.get(KnowledgeBase, base_id) is None
        audit = session.scalar(select(AuditLog))
        assert audit is not None and audit.resource_type == "knowledge_base"
        assert audit.detail == {"name": "删除审计资料库", "confirmed": True}
