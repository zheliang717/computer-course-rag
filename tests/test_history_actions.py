"""Navigation cards survive persistent history and stay account-scoped."""

from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.history import PersistentHistory
from app.models import User


def test_persistent_history_stores_actions_for_owner_only() -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    owner_id, outsider_id, course_id = uuid4(), uuid4(), uuid4()
    with sessions.begin() as session:
        session.add_all([
            User(id=owner_id, username="history_owner", display_name="Owner", role="student", password_hash="x"),
            User(id=outsider_id, username="history_outsider", display_name="Outsider", role="student", password_hash="x"),
        ])
    history = PersistentHistory(sessions)
    conversation = history.ensure_conversation(
        conversation_id=None, user_id=owner_id, knowledge_base_id=None, first_question="今天有什么课？",
    )
    action = {"kind": "course", "target_id": str(course_id), "title": "数据结构", "detail": "打开课程"}
    created = history.create(
        knowledge_base_id=None, conversation_id=conversation.id, user_id=owner_id,
        question="今天有什么课？", answer="请查看课程", message="平台数据", model="platform-data",
        accepted=True, citations=[], actions=[action],
    )
    assert created.actions == [action]
    assert history.list(knowledge_base_id=None, limit=10, user_id=owner_id,
                        conversation_id=conversation.id)[0].actions == [action]
    assert history.list(knowledge_base_id=None, limit=10, user_id=outsider_id,
                        conversation_id=conversation.id) == []
    assert history.ensure_conversation(conversation_id=conversation.id, user_id=outsider_id,
                                       knowledge_base_id=None, first_question="test") is None
