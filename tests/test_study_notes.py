"""Published-page notes stay private and cannot be forged across courses."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.auth import Principal
from app.database import Base
from app.models import (
    Chunk, Course, CourseEnrollment, CourseKnowledgeBase, Document, DocumentPage, KnowledgeBase, User,
)
from app.study_notes import StudyNoteService


class _TestAuth:
    required = True

    def __init__(self, principals):
        self.principals = principals

    def verify_token(self, token):
        return self.principals.get(token)


def test_study_note_requires_real_published_excerpt_and_student_ownership(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    student_id, outsider_id, teacher_id = uuid4(), uuid4(), uuid4()
    course_id, base_id, document_id = uuid4(), uuid4(), uuid4()
    excerpt = "二叉树的每个结点最多有两个子结点。"
    with sessions.begin() as session:
        session.add_all([
            User(id=student_id, username="note_student", display_name="学生", role="student", password_hash="x"),
            User(id=outsider_id, username="note_outsider", display_name="外部学生", role="student", password_hash="x"),
            User(id=teacher_id, username="note_teacher", display_name="教师", role="teacher", password_hash="x"),
            Course(id=course_id, title="数据结构", code="DSA-NOTE", status="published", owner_id=teacher_id),
            KnowledgeBase(id=base_id, name="数据结构资料", course="数据结构"),
        ])
        session.flush()
        session.add_all([
            CourseEnrollment(course_id=course_id, user_id=student_id, status="active"),
            CourseKnowledgeBase(course_id=course_id, knowledge_base_id=base_id),
            Document(id=document_id, knowledge_base_id=base_id, filename="数据结构讲义", publication_status="published", status="ready"),
        ])
        session.flush()
        session.add(DocumentPage(document_id=document_id, page_number=7, content=f"第一节。\n{excerpt}\n这是基本定义。"))
        session.add(Chunk(document_id=document_id, page_number=9, position=0, content=f"旧版索引页：{excerpt}"))

    monkeypatch.setattr(main_module, "study_notes", StudyNoteService(sessions))
    monkeypatch.setattr(main_module, "auth", _TestAuth({
        "student": Principal(id=str(student_id), username="note_student", display_name="学生", role="student"),
        "outsider": Principal(id=str(outsider_id), username="note_outsider", display_name="外部学生", role="student"),
        "teacher": Principal(id=str(teacher_id), username="note_teacher", display_name="教师", role="teacher"),
    }))
    client = TestClient(main_module.app)
    payload = {"course_id": str(course_id), "document_id": str(document_id), "page_number": 7,
               "excerpt": excerpt, "content": "每个结点最多有两个孩子。", "origin": "assistant"}
    assert client.post("/api/v1/study-notes", headers={"Authorization": "Bearer teacher"}, json=payload).status_code == 403
    assert client.post("/api/v1/study-notes", headers={"Authorization": "Bearer outsider"}, json=payload).status_code == 404
    assert client.post("/api/v1/study-notes", headers={"Authorization": "Bearer student"},
                       json={**payload, "excerpt": "这是错误课程资料中的一段伪造原文。"}).status_code == 422
    assert client.post("/api/v1/study-notes", headers={"Authorization": "Bearer student"},
                       json={**payload, "page_number": 8}).status_code == 404

    created = client.post("/api/v1/study-notes", headers={"Authorization": "Bearer student"}, json=payload)
    assert created.status_code == 201 and created.json()["source_available"] is True
    note_id = created.json()["id"]
    legacy = client.post("/api/v1/study-notes", headers={"Authorization": "Bearer student"},
                         json={**payload, "page_number": 9})
    assert legacy.status_code == 201 and legacy.json()["source_available"] is True
    assert len(client.get("/api/v1/study-notes", headers={"Authorization": "Bearer student"}).json()) == 2
    assert client.get("/api/v1/study-notes", headers={"Authorization": "Bearer outsider"}).json() == []
    assert client.delete(f"/api/v1/study-notes/{note_id}", headers={"Authorization": "Bearer outsider"}).status_code == 404

    with sessions.begin() as session:
        session.get(Document, document_id).publication_status = "archived"
    notes = client.get("/api/v1/study-notes", headers={"Authorization": "Bearer student"}).json()
    assert len(notes) == 2 and all(item["source_available"] is False for item in notes)
    assert client.post("/api/v1/study-notes", headers={"Authorization": "Bearer student"}, json=payload).status_code == 404
    with sessions.begin() as session:
        session.query(CourseEnrollment).filter_by(course_id=course_id, user_id=student_id).one().status = "removed"
    assert client.get("/api/v1/study-notes", headers={"Authorization": "Bearer student"}).json() == []
    assert client.delete(f"/api/v1/study-notes/{note_id}", headers={"Authorization": "Bearer student"}).status_code == 204
