"""Publishing a document never implies approval to send excerpts to a model."""

from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.auth import AuthService, Principal
from app.catalog import KnowledgeCatalog
from app.database import Base
from app.domain import SearchHit, TextChunk
from app.history import MemoryHistory
from app.models import AuditLog, Document, KnowledgeBase, User
from app.rag import RetrievalResult


def _setup():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    admin_id, teacher_id, student_id, base_id, document_id = (uuid4() for _ in range(5))
    with sessions.begin() as session:
        session.add_all([
            User(id=admin_id, username="sharing_admin", display_name="Admin", role="admin", password_hash="x"),
            User(id=teacher_id, username="sharing_teacher", display_name="Teacher", role="teacher", password_hash="x"),
            User(id=student_id, username="sharing_student", display_name="Student", role="student", password_hash="x"),
            KnowledgeBase(id=base_id, name="操作系统", course="操作系统"),
        ])
        session.flush()
        session.add(Document(id=document_id, knowledge_base_id=base_id, filename="课程讲义", status="ready",
                             publication_status="published", source_url="https://example.org/book",
                             license_name="CC BY 4.0", license_url="https://creativecommons.org/licenses/by/4.0/"))
    return sessions, admin_id, teacher_id, student_id, base_id, document_id


def test_admin_approval_requires_confirmation_and_audits_atomically(monkeypatch) -> None:
    sessions, admin_id, teacher_id, _student_id, _base_id, document_id = _setup()
    catalog = KnowledgeCatalog(sessions)
    auth = AuthService(sessions, secret="sharing-secret", required=True)
    monkeypatch.setattr(main_module, "catalog", catalog)
    monkeypatch.setattr(main_module, "auth", auth)
    client = TestClient(main_module.app)
    admin = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(admin_id), username="sharing_admin", display_name="Admin", role="admin"))}
    teacher = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(teacher_id), username="sharing_teacher", display_name="Teacher", role="teacher"))}
    path = f"/api/v1/admin/documents/{document_id}/external-sharing"
    payload = {"allowed": True, "reason": "已核验来源与许可条款，可用于本地演示外发", "confirmed": True}
    assert client.put(path, headers=teacher, json=payload).status_code == 403
    assert client.put(path, headers=admin, json={**payload, "confirmed": False}).status_code == 409
    assert client.put(path, headers=admin, json=payload).json()["external_model_allowed"] is True
    assert catalog.externally_approved_document_ids({document_id}) == {document_id}
    with sessions() as session:
        audit = session.scalar(select(AuditLog))
        assert audit.action == "approve_external_share" and audit.detail["reason"] == payload["reason"]

    catalog.update_document(document_id, license_name="许可变更，须重新审核")
    assert catalog.externally_approved_document_ids({document_id}) == set()
    with sessions() as session:
        assert session.get(Document, document_id).external_model_allowed is False

    catalog.set_external_sharing(document_id, allowed=True, reason="已对更新后的许可重新核验",
                                 actor_id=admin_id, actor_name="Admin")
    catalog.ensure_document(document_id=str(document_id), knowledge_base_id=_base_id, filename="课程讲义")
    with sessions() as session:
        refreshed = session.get(Document, document_id)
        assert refreshed.external_model_allowed is False and refreshed.status == "pending"


def test_approval_rolls_back_when_audit_fails() -> None:
    sessions, admin_id, _teacher_id, _student_id, _base_id, document_id = _setup()
    catalog = KnowledgeCatalog(sessions)

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    event.listen(AuditLog, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit failed"):
            catalog.set_external_sharing(document_id, allowed=True, reason="已核验许可和范围",
                                         actor_id=admin_id, actor_name="Admin")
    finally:
        event.remove(AuditLog, "before_insert", fail_audit)
    with sessions() as session:
        assert session.get(Document, document_id).external_model_allowed is False
        assert session.scalar(select(AuditLog)) is None


def test_metadata_change_and_approval_revocation_roll_back_with_audit_failure() -> None:
    sessions, admin_id, _teacher_id, _student_id, _base_id, document_id = _setup()
    catalog = KnowledgeCatalog(sessions)
    catalog.set_external_sharing(document_id, allowed=True, reason="已核验许可和范围",
                                 actor_id=admin_id, actor_name="Admin")

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("metadata audit failed")

    event.listen(AuditLog, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="metadata audit failed"):
            catalog.update_document(document_id, license_url="https://example.org/updated-license",
                                    actor_id=admin_id, actor_name="Admin")
    finally:
        event.remove(AuditLog, "before_insert", fail_audit)
    with sessions() as session:
        document = session.get(Document, document_id)
        assert document.license_url == "https://creativecommons.org/licenses/by/4.0/"
        assert document.external_model_allowed is True
        audits = session.scalars(select(AuditLog)).all()
        assert len(audits) == 1 and audits[0].action == "approve_external_share"


def test_document_metadata_api_revokes_approval_and_records_changed_fields(monkeypatch) -> None:
    sessions, admin_id, _teacher_id, _student_id, _base_id, document_id = _setup()
    catalog = KnowledgeCatalog(sessions)
    catalog.set_external_sharing(document_id, allowed=True, reason="已核验许可和范围",
                                 actor_id=admin_id, actor_name="Admin")
    auth = AuthService(sessions, secret="metadata-audit", required=True)
    monkeypatch.setattr(main_module, "catalog", catalog)
    monkeypatch.setattr(main_module, "auth", auth)
    admin = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(admin_id), username="sharing_admin", display_name="Admin", role="admin"))}
    response = TestClient(main_module.app).patch(
        f"/api/v1/documents/{document_id}", headers=admin,
        json={"license_url": "https://example.org/updated-license"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["external_model_allowed"] is False
    with sessions() as session:
        audits = session.scalars(select(AuditLog).order_by(AuditLog.created_at)).all()
        assert [audit.action for audit in audits] == ["approve_external_share", "update"]
        assert audits[-1].detail["changed_fields"] == ["license_url"]


def test_unapproved_evidence_stays_local_and_passage_cannot_be_sent(monkeypatch) -> None:
    sessions, admin_id, _teacher_id, student_id, _base_id, document_id = _setup()
    catalog = KnowledgeCatalog(sessions)
    auth = AuthService(sessions, secret="sharing-answer-secret", required=True)
    student = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(student_id), username="sharing_student", display_name="Student", role="student"))}
    hit = SearchHit(TextChunk(chunk_id=str(uuid4()), document_id=str(document_id),
                              document_name="课程讲义", page_number=1, text="进程是运行中的程序。"), score=0.9)

    class Generator:
        calls = []

        def generate(self, question, hits, **kwargs):
            self.calls.append((question, hits, kwargs))
            return "模型回答"

    generator = Generator()
    monkeypatch.setattr(main_module, "catalog", catalog)
    monkeypatch.setattr(main_module, "auth", auth)
    monkeypatch.setattr(main_module, "history", MemoryHistory())
    monkeypatch.setattr(main_module, "student_agenda", None)
    monkeypatch.setattr(main_module, "model_usage", None)
    monkeypatch.setattr(main_module, "settings", main_module.settings.model_copy(update={"llm_provider": "compatible"}))
    monkeypatch.setattr(main_module, "generator", generator)
    monkeypatch.setattr(main_module, "_retrieve_for_user", lambda *_, **kwargs: RetrievalResult(True, "找到证据", [hit]))
    monkeypatch.setattr(main_module, "_require_knowledge_base_access", lambda *_: None)
    monkeypatch.setattr(main_module, "_resolve_assistant_context", lambda *args, **kwargs: None)
    client = TestClient(main_module.app)
    request = {"question": "什么是进程？", "answer_mode": "rag"}
    local = client.post("/api/v1/questions/ask", headers=student, json=request)
    assert local.status_code == 200, local.text
    assert local.json()["model"] == "local-evidence" and local.json()["citations"]
    assert generator.calls == []
    conversation_id = local.json()["conversation_id"]
    follow_up = client.post("/api/v1/questions/ask", headers=student, json={
        "question": "再说明一下", "answer_mode": "general", "conversation_id": conversation_id,
    })
    assert follow_up.status_code == 409 and generator.calls == []
    follow_up = client.post("/api/v1/questions/ask", headers=student, json={
        "question": "再说明一下", "answer_mode": "general",
    })
    assert follow_up.status_code == 200 and follow_up.json()["conversation_id"] != conversation_id
    assert "进程是运行中的程序" not in generator.calls[-1][0]
    assert "本地资料证据" not in generator.calls[-1][0]
    passage = client.post("/api/v1/questions/ask", headers=student, json={
        **request, "source_document_id": str(document_id), "question": "解释选段：进程是运行中的程序。",
    })
    assert passage.status_code == 409 and len(generator.calls) == 1

    catalog.set_external_sharing(document_id, allowed=True, reason="许可及服务范围已核验",
                                 actor_id=admin_id, actor_name="Admin")
    online = client.post("/api/v1/questions/ask", headers=student, json={**request, "conversation_id": conversation_id})
    assert online.status_code == 200 and online.json()["answer"] == "模型回答"
    assert len(generator.calls) == 2 and generator.calls[-1][1] == [hit]
    records = main_module.history.conversation_context(UUID(conversation_id), user_id=student_id)
    assert records[-1].external_context_safe is True
    assert records[-1].context_document_ids == [str(document_id)]

    catalog.set_external_sharing(document_id, allowed=False, reason="撤销资料外发资格",
                                 actor_id=admin_id, actor_name="Admin")
    assert main_module._safe_online_context(records[-1:]) == []


def test_model_timeout_falls_back_without_reusing_fallback_history(monkeypatch) -> None:
    sessions, admin_id, _teacher_id, student_id, _base_id, document_id = _setup()
    catalog = KnowledgeCatalog(sessions)
    catalog.set_external_sharing(document_id, allowed=True, reason="许可及服务范围已核验",
                                 actor_id=admin_id, actor_name="Admin")
    auth = AuthService(sessions, secret="timeout-fallback", required=True)
    student = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(student_id), username="sharing_student", display_name="Student", role="student"))}
    hit = SearchHit(TextChunk(chunk_id=str(uuid4()), document_id=str(document_id),
                              document_name="课程讲义", page_number=1, text="进程是运行中的程序。"), score=0.9)

    class Generator:
        calls = []

        def generate(self, question, hits, **kwargs):
            self.calls.append((question, hits, kwargs))
            if len(self.calls) == 1:
                raise httpx.ReadTimeout("model timed out")
            return "在线追问回答"

    generator = Generator()
    monkeypatch.setattr(main_module, "catalog", catalog)
    monkeypatch.setattr(main_module, "auth", auth)
    monkeypatch.setattr(main_module, "history", MemoryHistory())
    monkeypatch.setattr(main_module, "student_agenda", None)
    monkeypatch.setattr(main_module, "model_usage", None)
    monkeypatch.setattr(main_module, "settings", main_module.settings.model_copy(update={
        "llm_provider": "compatible", "llm_fallback_offline": True,
    }))
    monkeypatch.setattr(main_module, "generator", generator)
    monkeypatch.setattr(main_module, "_retrieve_for_user", lambda *_, **kwargs: RetrievalResult(True, "找到证据", [hit]))
    monkeypatch.setattr(main_module, "_require_knowledge_base_access", lambda *_: None)
    client = TestClient(main_module.app)
    fallback = client.post("/api/v1/questions/ask", headers=student,
                           json={"question": "什么是进程？", "answer_mode": "rag"})
    assert fallback.status_code == 200, fallback.text
    assert fallback.json()["model"] == "offline-fallback"
    assert "在线模型暂不可用" in fallback.json()["message"]
    conversation_id = fallback.json()["conversation_id"]
    records = main_module.history.conversation_context(UUID(conversation_id), user_id=student_id)
    assert records[-1].external_context_safe is False

    follow_up = client.post("/api/v1/questions/ask", headers=student, json={
        "question": "继续解释", "answer_mode": "general", "conversation_id": conversation_id,
    })
    assert follow_up.status_code == 409
    follow_up = client.post("/api/v1/questions/ask", headers=student, json={
        "question": "继续解释", "answer_mode": "general",
    })
    assert follow_up.status_code == 200 and follow_up.json()["conversation_id"] != conversation_id
    assert "进程是运行中的程序" not in generator.calls[-1][0]


@pytest.mark.parametrize("failure_type, expected_status, expected_detail", [
    (httpx.ConnectTimeout, 504, "模型响应超时，本次未生成回答；请稍后重试。"),
    (httpx.ConnectError, 502, "无法连接模型服务，本次未生成回答；请稍后重试。"),
])
def test_model_network_failure_without_fallback_returns_error_and_finishes_usage(
    monkeypatch, failure_type, expected_status, expected_detail,
) -> None:
    sessions, admin_id, _teacher_id, student_id, _base_id, document_id = _setup()
    catalog = KnowledgeCatalog(sessions)
    catalog.set_external_sharing(document_id, allowed=True, reason="许可及服务范围已核验",
                                 actor_id=admin_id, actor_name="Admin")
    auth = AuthService(sessions, secret="timeout-no-fallback", required=True)
    student = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(student_id), username="sharing_student", display_name="Student", role="student"))}
    hit = SearchHit(TextChunk(chunk_id=str(uuid4()), document_id=str(document_id),
                              document_name="课程讲义", page_number=1, text="进程是运行中的程序。"), score=0.9)

    class Generator:
        def generate(self, *_args, **_kwargs):
            raise failure_type("model unavailable")

    class Usage:
        completions = []

        def reserve(self, **_kwargs):
            return uuid4()

        def finish(self, reservation_id, **kwargs):
            self.completions.append((reservation_id, kwargs))

    usage = Usage()
    monkeypatch.setattr(main_module, "catalog", catalog)
    monkeypatch.setattr(main_module, "auth", auth)
    history = MemoryHistory()
    monkeypatch.setattr(main_module, "history", history)
    monkeypatch.setattr(main_module, "student_agenda", None)
    monkeypatch.setattr(main_module, "model_usage", usage)
    monkeypatch.setattr(main_module, "settings", main_module.settings.model_copy(update={
        "llm_provider": "compatible", "llm_fallback_offline": False,
    }))
    monkeypatch.setattr(main_module, "generator", Generator())
    monkeypatch.setattr(main_module, "_retrieve_for_user", lambda *_, **kwargs: RetrievalResult(True, "找到证据", [hit]))
    monkeypatch.setattr(main_module, "_require_knowledge_base_access", lambda *_: None)
    response = TestClient(main_module.app).post("/api/v1/questions/ask", headers=student,
                                               json={"question": "什么是进程？", "answer_mode": "rag"})
    assert response.status_code == expected_status and response.json()["detail"] == expected_detail
    assert len(usage.completions) == 1
    assert usage.completions[0][1]["successful"] is False
    assert usage.completions[0][1]["error_type"] == failure_type.__name__
    assert history.list(knowledge_base_id=None, limit=10, user_id=student_id) == []
    assert history.list_conversations(user_id=student_id) == []


def test_mixed_evidence_only_sends_approved_document(monkeypatch) -> None:
    sessions, admin_id, _teacher_id, student_id, base_id, approved_id = _setup()
    other_id = uuid4()
    with sessions.begin() as session:
        session.add(Document(id=other_id, knowledge_base_id=base_id, filename="未授权资料", status="ready",
                             publication_status="published", source_url="https://example.org/other",
                             license_name="待核验", license_url="https://example.org/license"))
    catalog = KnowledgeCatalog(sessions)
    catalog.set_external_sharing(approved_id, allowed=True, reason="许可和服务范围已核验",
                                 actor_id=admin_id, actor_name="Admin")
    auth = AuthService(sessions, secret="mixed-evidence", required=True)
    student = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(student_id), username="sharing_student", display_name="Student", role="student"))}
    hits = [
        SearchHit(TextChunk(chunk_id=str(uuid4()), document_id=str(other_id),
                            document_name="未授权资料", page_number=1, text="不能外发的片段"), score=0.95),
        SearchHit(TextChunk(chunk_id=str(uuid4()), document_id=str(approved_id),
                            document_name="课程讲义", page_number=2, text="可外发的片段"), score=0.8),
    ]

    class Generator:
        calls = []

        def generate(self, question, evidence, **kwargs):
            self.calls.append((question, evidence, kwargs))
            return "模型回答"

    generator = Generator()
    monkeypatch.setattr(main_module, "catalog", catalog)
    monkeypatch.setattr(main_module, "auth", auth)
    monkeypatch.setattr(main_module, "history", MemoryHistory())
    monkeypatch.setattr(main_module, "student_agenda", None)
    monkeypatch.setattr(main_module, "model_usage", None)
    monkeypatch.setattr(main_module, "settings", main_module.settings.model_copy(update={"llm_provider": "compatible"}))
    monkeypatch.setattr(main_module, "generator", generator)
    monkeypatch.setattr(main_module, "_retrieve_for_user", lambda *_, **kwargs: RetrievalResult(True, "找到证据", hits))
    monkeypatch.setattr(main_module, "_require_knowledge_base_access", lambda *_: None)
    result = TestClient(main_module.app).post("/api/v1/questions/ask", headers=student,
                                              json={"question": "解释概念", "answer_mode": "rag"})
    assert result.status_code == 200, result.text
    assert "已排除 1 条" in result.json()["message"]
    assert [item["document_id"] for item in result.json()["citations"]] == [str(approved_id)]
    assert generator.calls[0][1] == [hits[1]]


def test_revocation_during_model_reservation_blocks_outbound_evidence(monkeypatch) -> None:
    sessions, admin_id, _teacher_id, student_id, _base_id, document_id = _setup()
    catalog = KnowledgeCatalog(sessions)
    catalog.set_external_sharing(document_id, allowed=True, reason="许可及服务范围已核验",
                                 actor_id=admin_id, actor_name="Admin")
    auth = AuthService(sessions, secret="revocation-race", required=True)
    student = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(student_id), username="sharing_student", display_name="Student", role="student"))}
    hit = SearchHit(TextChunk(chunk_id=str(uuid4()), document_id=str(document_id),
                             document_name="课程讲义", page_number=1, text="仅在授权期间可外发。"), score=0.9)

    class Usage:
        completions = []

        def reserve(self, **_kwargs):
            catalog.set_external_sharing(document_id, allowed=False, reason="管理员撤销许可",
                                         actor_id=admin_id, actor_name="Admin")
            return uuid4()

        def finish(self, reservation_id, **kwargs):
            self.completions.append((reservation_id, kwargs))

    class Generator:
        calls = 0

        def generate(self, *_args, **_kwargs):
            self.calls += 1
            return "不应生成"

    usage, generator = Usage(), Generator()
    monkeypatch.setattr(main_module, "catalog", catalog)
    monkeypatch.setattr(main_module, "auth", auth)
    monkeypatch.setattr(main_module, "history", MemoryHistory())
    monkeypatch.setattr(main_module, "student_agenda", None)
    monkeypatch.setattr(main_module, "model_usage", usage)
    monkeypatch.setattr(main_module, "settings", main_module.settings.model_copy(update={"llm_provider": "compatible"}))
    monkeypatch.setattr(main_module, "generator", generator)
    monkeypatch.setattr(main_module, "_retrieve_for_user", lambda *_, **kwargs: RetrievalResult(True, "找到证据", [hit]))
    monkeypatch.setattr(main_module, "_require_knowledge_base_access", lambda *_: None)
    response = TestClient(main_module.app).post("/api/v1/questions/ask", headers=student,
                                                json={"question": "解释授权讲义", "answer_mode": "rag"})
    assert response.status_code == 409
    assert "未调用模型" in response.json()["detail"]
    assert generator.calls == 0
    assert len(usage.completions) == 1
    assert usage.completions[0][1]["error_type"] == "ExternalApprovalRevoked"
    assert usage.completions[0][1]["successful"] is False
