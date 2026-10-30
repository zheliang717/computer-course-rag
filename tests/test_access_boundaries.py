"""Regression tests for private tutor feedback and course-scoped moderation."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.auth import Principal
from app.database import Base
from app.history import PersistentHistory
from app.models import KnowledgeBase, QuestionRecord, User
from app.moderation import QuestionModerationService


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


class _TestAuth:
    required = True

    def __init__(self, principals: dict[str, Principal]):
        self.principals = principals

    def verify_token(self, token: str):
        return self.principals.get(token)


def _principal(user_id: UUID, role: str) -> Principal:
    return Principal(id=str(user_id), username=role, display_name=role, role=role)


def test_feedback_only_changes_own_tutor_record(monkeypatch, postgres_sessions) -> None:
    sessions = postgres_sessions
    owner_id, other_id = uuid4(), uuid4()
    with sessions.begin() as session:
        session.add_all([
            User(id=owner_id, username="owner", display_name="Owner", role="student", password_hash="x"),
            User(id=other_id, username="other", display_name="Other", role="student", password_hash="x"),
        ])
    private_history = PersistentHistory(sessions)
    record = private_history.create(
        knowledge_base_id=None, question="private", answer="answer", message="ok", model="offline",
        accepted=True, citations=[], user_id=owner_id,
    )
    monkeypatch.setattr(main_module, "history", private_history)
    monkeypatch.setattr(main_module, "auth", _TestAuth({
        "owner": _principal(owner_id, "student"), "other": _principal(other_id, "student"),
    }))
    client = TestClient(main_module.app)

    denied = client.post(
        f"/api/v1/history/{record.id}/feedback", headers={"Authorization": "Bearer other"},
        json={"rating": 1, "feedback": "not mine"},
    )
    assert denied.status_code == 404
    assert private_history.list(knowledge_base_id=None, limit=10, user_id=owner_id)[0].rating is None
    assert private_history.list(knowledge_base_id=None, limit=10, user_id=other_id) == []

    accepted = client.post(
        f"/api/v1/history/{record.id}/feedback", headers={"Authorization": "Bearer owner"},
        json={"rating": 5, "feedback": "helpful"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["rating"] == 5


def test_teacher_moderation_is_limited_to_accessible_knowledge_base(monkeypatch, postgres_sessions) -> None:
    sessions = postgres_sessions
    teacher_id, student_id, admin_id = uuid4(), uuid4(), uuid4()
    own_base_id, other_base_id = uuid4(), uuid4()
    own_record_id, other_record_id = uuid4(), uuid4()
    with sessions.begin() as session:
        session.add_all([
            User(id=teacher_id, username="teacher", display_name="Teacher", role="teacher", password_hash="x"),
            User(id=student_id, username="student", display_name="Student", role="student", password_hash="x"),
            User(id=admin_id, username="admin", display_name="Admin", role="admin", password_hash="x"),
        ])
        session.flush()
        session.add_all([
            KnowledgeBase(id=own_base_id, name="Own", course="Own", created_by=teacher_id),
            KnowledgeBase(id=other_base_id, name="Other", course="Other"),
        ])
        session.flush()
        session.add_all([
            QuestionRecord(id=own_record_id, knowledge_base_id=own_base_id, user_id=student_id,
                           question="own", answer="answer", message="ok", model="offline",
                           accepted=True, citations=[]),
            QuestionRecord(id=other_record_id, knowledge_base_id=other_base_id, user_id=student_id,
                           question="other", answer="answer", message="ok", model="offline",
                           accepted=True, citations=[]),
        ])

    class _Access:
        def accessible_knowledge_base_ids(self, *, user_id, role):
            assert user_id == teacher_id and role == "teacher"
            return {own_base_id}

    monkeypatch.setattr(main_module, "catalog", object())
    monkeypatch.setattr(main_module, "analytics", _Access())
    monkeypatch.setattr(main_module, "moderation", QuestionModerationService(sessions, embedder=None))
    monkeypatch.setattr(main_module, "admin_service", None)
    monkeypatch.setattr(main_module, "auth", _TestAuth({
        "teacher": _principal(teacher_id, "teacher"), "admin": _principal(admin_id, "admin"),
    }))
    client = TestClient(main_module.app)
    teacher_headers = {"Authorization": "Bearer teacher"}
    admin_headers = {"Authorization": "Bearer admin"}

    teacher_items = client.get("/api/v1/question-reviews", headers=teacher_headers)
    assert teacher_items.status_code == 200
    assert {item["id"] for item in teacher_items.json()} == {str(own_record_id)}
    admin_items = client.get("/api/v1/question-reviews", headers=admin_headers)
    assert admin_items.status_code == 200
    assert {item["id"] for item in admin_items.json()} == {str(own_record_id), str(other_record_id)}

    denied = client.patch(
        f"/api/v1/question-reviews/{other_record_id}", headers=teacher_headers,
        json={"status": "approved", "publish_to_knowledge_base": False},
    )
    assert denied.status_code == 404

    allowed = client.patch(
        f"/api/v1/question-reviews/{own_record_id}", headers=teacher_headers,
        json={"status": "approved", "publish_to_knowledge_base": False},
    )
    assert allowed.status_code == 200
    assert allowed.json()["review_status"] == "approved"
