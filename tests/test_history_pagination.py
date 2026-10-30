"""Assistant history pagination preserves order and account isolation."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.auth import Principal
from app.database import Base
from app.history import MemoryHistory, PersistentHistory
from app.models import QuestionRecord, TutorConversation, User


class _Auth:
    required = True

    def __init__(self, principals):
        self.principals = principals

    def verify_token(self, token):
        return self.principals.get(token)


def test_persistent_conversation_pages_are_stable_and_isolated(monkeypatch, postgres_sessions) -> None:
    sessions = postgres_sessions
    student_id, other_id = uuid4(), uuid4()
    stamp = datetime(2026, 10, 2, tzinfo=timezone.utc)
    own = [TutorConversation(id=uuid4(), user_id=student_id, title=f"对话 {index}",
                             updated_at=stamp + timedelta(minutes=index // 2)) for index in range(25)]
    foreign = TutorConversation(id=uuid4(), user_id=other_id, title="其他学生的对话", updated_at=stamp)
    failed_empty = TutorConversation(id=uuid4(), user_id=student_id, title="模型失败的空会话",
                                     updated_at=stamp + timedelta(hours=1))
    with sessions.begin() as session:
        session.add_all([
            User(id=student_id, username="page_student", display_name="Student", role="student", password_hash="x"),
            User(id=other_id, username="page_other", display_name="Other", role="student", password_hash="x"),
        ])
        session.flush()
        session.add_all([*own, foreign, failed_empty])
        session.flush()
        session.add_all([QuestionRecord(id=uuid4(), conversation_id=item.id, user_id=item.user_id,
                                        question=item.title, answer="已回答", message="完成", model="offline",
                                        accepted=True, citations=[], created_at=item.updated_at) for item in [*own, foreign]])

    history = PersistentHistory(sessions)
    expected = [str(item.id) for item in sorted(own, key=lambda item: (item.updated_at, item.id), reverse=True)]
    monkeypatch.setattr(main_module, "history", history)
    monkeypatch.setattr(main_module, "auth", _Auth({
        "student": Principal(id=str(student_id), username="page_student", display_name="Student", role="student"),
        "other": Principal(id=str(other_id), username="page_other", display_name="Other", role="student"),
    }))
    client = TestClient(main_module.app)
    headers = {"Authorization": "Bearer student"}
    page1 = client.get("/api/v1/tutor/conversations?limit=10", headers=headers)
    assert page1.status_code == 200
    ids1 = [item["id"] for item in page1.json()]
    page2 = client.get(f"/api/v1/tutor/conversations?limit=10&before={ids1[-1]}", headers=headers)
    assert page2.status_code == 200
    ids2 = [item["id"] for item in page2.json()]
    page3 = client.get(f"/api/v1/tutor/conversations?limit=10&before={ids2[-1]}", headers=headers)
    assert page3.status_code == 200
    ids3 = [item["id"] for item in page3.json()]
    assert ids1 + ids2 + ids3 == expected
    assert str(failed_empty.id) not in ids1 + ids2 + ids3
    assert len(ids3) == 5
    assert client.get(f"/api/v1/tutor/conversations?before={failed_empty.id}", headers=headers).status_code == 409
    assert client.get(f"/api/v1/tutor/conversations?before={foreign.id}", headers=headers).status_code == 409
    assert client.get("/api/v1/tutor/conversations?limit=0", headers=headers).status_code == 422
    assert client.get("/api/v1/tutor/conversations?limit=101", headers=headers).status_code == 422
    assert len(client.get("/api/v1/tutor/conversations", headers={"Authorization": "Bearer other"}).json()) == 1


def test_memory_conversation_cursor_keeps_same_account() -> None:
    history = MemoryHistory()
    student_id, other_id = uuid4(), uuid4()
    first = history.ensure_conversation(conversation_id=None, user_id=student_id,
                                        knowledge_base_id=None, first_question="第一条")
    second = history.ensure_conversation(conversation_id=None, user_id=student_id,
                                         knowledge_base_id=None, first_question="第二条")
    foreign = history.ensure_conversation(conversation_id=None, user_id=other_id,
                                          knowledge_base_id=None, first_question="其他学生")
    assert first is not None and second is not None and foreign is not None
    empty = history.ensure_conversation(conversation_id=None, user_id=student_id,
                                        knowledge_base_id=None, first_question="模型失败")
    assert empty is not None
    for item, owner in ((first, student_id), (second, student_id), (foreign, other_id)):
        history.create(knowledge_base_id=None, conversation_id=item.id, user_id=owner,
                       question=item.title, answer="已回答", message="完成", model="offline",
                       accepted=True, citations=[])
    first_page = history.list_conversations(user_id=student_id, limit=1)
    second_page = history.list_conversations(user_id=student_id, limit=1, before=UUID(first_page[0]["id"]))
    assert {first_page[0]["id"], second_page[0]["id"]} == {str(first.id), str(second.id)}
    assert str(empty.id) not in {first_page[0]["id"], second_page[0]["id"]}
    assert history.list_conversations(user_id=student_id, before=foreign.id) == []
    assert history.list_conversations(user_id=student_id, before=empty.id) == []
