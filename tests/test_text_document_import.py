"""Sourced text imports enter the governed document catalog with external sharing off."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.auth import AuthService, Principal
from app.catalog import KnowledgeCatalog, stable_document_uuid
from app.database import Base
from app.models import AuditLog, Chunk, Document, KnowledgeBase, User
from app.ingestion_jobs import DocumentIngestionService


class _CatalogStore:
    def __init__(self, sessions):
        self.sessions = sessions

    @property
    def size(self):
        with self.sessions() as session:
            return session.scalar(select(func.count(Chunk.id))) or 0

    def add(self, chunks):
        document_id = stable_document_uuid(chunks[0].document_id)
        with self.sessions.begin() as session:
            document = session.get(Document, document_id)
            session.execute(delete(Chunk).where(Chunk.document_id == document_id))
            session.add_all([
                Chunk(document_id=document_id, page_number=item.page_number,
                      chapter=item.chapter, position=index, content=item.text,
                      content_metadata={}, embedding=None)
                for index, item in enumerate(chunks)
            ])
            document.page_count = max(item.page_number for item in chunks)
            document.status = "ready"

    def prepare_vectors(self,chunks):return [None for _ in chunks]


def test_text_document_import_is_governed_and_idempotent(monkeypatch):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    admin_id, student_id, base_id, other_base_id = (uuid4() for _ in range(4))
    with sessions.begin() as session:
        session.add_all([
            User(id=admin_id, username="text_admin", display_name="Admin", role="admin", password_hash="x"),
            User(id=student_id, username="text_student", display_name="Student", role="student", password_hash="x"),
            KnowledgeBase(id=base_id, name="操作系统", course="操作系统"),
            KnowledgeBase(id=other_base_id, name="计算机网络", course="计算机网络"),
        ])
    catalog = KnowledgeCatalog(sessions)
    auth = AuthService(sessions, secret="text-import-secret", required=True)
    monkeypatch.setattr(main_module, "catalog", catalog)
    monkeypatch.setattr(main_module, "auth", auth)
    test_store=_CatalogStore(sessions)
    monkeypatch.setattr(main_module, "store", test_store)
    monkeypatch.setattr(main_module,'ingestion_jobs',DocumentIngestionService(sessions,catalog,test_store,chunk_size=500,chunk_overlap=80))
    admin = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(admin_id), username="text_admin", display_name="Admin", role="admin"))}
    student = {"Authorization": "Bearer " + auth.issue_token(Principal(
        id=str(student_id), username="text_student", display_name="Student", role="student"))}
    client = TestClient(main_module.app)
    path = f"/api/v1/knowledge-bases/{base_id}/text-documents"
    payload = {
        "document_id": "open-lecture:address-space:fixed-commit",
        "title": "操作系统课程：地址空间",
        "source_url": "https://example.org/fixed-lecture",
        "license_name": "MIT",
        "license_url": "https://example.org/fixed-license",
        "version_label": "2026 秋季 · 固定提交",
        "publication_status": "published",
        "pages": [
            {"page_number": 2, "chapter": "虚拟存储", "text": "虚拟地址空间将进程地址与物理内存分离，便于保护和共享。"},
            {"page_number": 1, "chapter": "地址", "text": "物理地址由系统总线使用；虚拟地址通过映射找到物理位置。"},
        ],
    }
    assert client.post(path, headers=student, json=payload).status_code == 403
    assert client.post(path, headers=admin, json={**payload, "pages": [payload["pages"][0]] * 2}).status_code == 422
    assert client.post(path, headers=admin, json={**payload, "source_url": ""}).status_code == 422
    with sessions() as session:
        assert session.scalar(select(func.count(Document.id))) == 0

    response = client.post(path, headers=admin, json=payload)
    assert response.status_code == 200, response.text
    item = response.json()["document"]
    assert item["name"] == payload["title"] and item["status"] == "ready"
    assert item["page_count"] == 2 and item["chunk_count"] > 0
    assert item["external_model_allowed"] is False
    assert item["source_url"] == payload["source_url"] and item["license_name"] == "MIT"
    content = client.get(f"/api/v1/documents/{item['id']}/content", headers=student)
    assert content.status_code == 200
    assert [page["page_number"] for page in content.json()["pages"]] == [1, 2]
    with sessions() as session:
        assert session.scalar(select(func.count(AuditLog.id))) == 1

    catalog.set_external_sharing(UUID(item["id"]), allowed=True, reason="已经核验授课资料外发范围",
                                 actor_id=admin_id, actor_name="Admin")
    changed = {**payload, "pages": [{"page_number": 1, "chapter": "地址", "text": "更新后的地址空间讲义正文，重新导入应撤销旧外发批准。"}]}
    response = client.post(path, headers=admin, json=changed)
    assert response.status_code == 200, response.text
    assert response.json()["document"]["external_model_allowed"] is False
    assert response.json()["document"]["page_count"] == 1
    assert client.post(f"/api/v1/knowledge-bases/{other_base_id}/text-documents",
                       headers=admin, json=payload).status_code == 409

    # Attribution remains readable without flooding the instructional index.
    reading = {**payload, "document_id": "reading:non-indexed-notice", "pages": [
        {"page_number": 1, "chapter": "正文", "text": "进程切换需要保存和恢复上下文。"},
        {"page_number": 2, "chapter": "许可", "text": "完整来源署名与许可条款仅用于阅读，不参与课程问答检索。", "index_for_retrieval": False},
    ]}
    response = client.post(path, headers=admin, json=reading)
    assert response.status_code == 200, response.text
    assert response.json()["document"]["page_count"] == 2
    content = client.get(f"/api/v1/documents/{response.json()['document']['id']}/content", headers=student).json()
    assert content["pages"][0]["chunks"]
    assert content["pages"][1]["content"] == reading["pages"][1]["text"]
    assert not content["pages"][1]["chunks"]
    with sessions() as session:
        before = session.scalar(select(func.count(Document.id)))
    rejected = client.post(path, headers=admin, json={**reading, "document_id": "reading:no-index",
        "pages": [reading["pages"][1]]})
    assert rejected.status_code == 422
    with sessions() as session:
        assert session.scalar(select(func.count(Document.id))) == before
    assert client.post(path, headers=admin, json={**reading, "document_id": "reading:invalid-split",
        "chunk_size": 100, "chunk_overlap": 100}).status_code == 422
    small = client.post(path, headers=admin, json={**reading, "document_id": "reading:small-split",
        "chunk_size": 180, "chunk_overlap": 40})
    assert small.status_code == 200, small.text
