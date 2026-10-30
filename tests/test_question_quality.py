"""Teacher question checks flag verifiable defects without pretending to grade semantics."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.auth import Principal
from app.database import Base
from app.models import Course, QuestionBankItem, TeachingDraft, User
from app.question_quality import review_question_set
from app.teaching_drafts import TeachingDraftService


def _question(stem: str, answer: str = "A") -> dict:
    return {"question_type": "single_choice", "stem": stem,
            "options": ["A. 左子树", "B. 右子树"], "correct_answer": answer,
            "explanation": "通过遍历顺序判断。", "difficulty": 2, "knowledge_point": "二叉树"}


def test_preflight_finds_duplicate_and_answer_mismatch_but_not_valid_questions() -> None:
    original = _question("中序遍历最先访问哪个子树？")
    repeated = _question("中序遍历最先访问哪个子树？", "C")
    repeated["options"] = ["A. 左子树", "B. 左子树"]
    findings = review_question_set([original, repeated], [{"id": "existing", "stem": original["stem"]}])
    errors = {(item["question_index"], item["code"]) for item in findings if item["severity"] == "error"}
    assert (1, "duplicate_in_bank") in errors
    assert (2, "duplicate_in_draft") in errors
    assert (2, "duplicate_options") in errors
    assert (2, "answer_not_in_options") in errors
    assert review_question_set([_question("后序遍历最后访问哪个结点？")]) == []
    unlabeled = _question("队列的出队顺序是什么？")
    unlabeled["options"] = ["先进先出", "后进先出"]
    assert review_question_set([unlabeled]) == []
    full_option = _question("栈的入栈操作改变哪个位置？", "A. 左子树")
    assert review_question_set([full_option]) == []


def test_preflight_checks_multiple_choice_and_warns_for_similar_bank_stem() -> None:
    multi = _question("栈和队列在数据访问方式与入队出队顺序上有哪些区别？", "A")
    multi["question_type"] = "multiple_choice"
    findings = review_question_set([multi], [{"id": "old", "stem": "栈和队列在数据访问方式与入队出队顺序上有什么区别？"}])
    assert {item["code"] for item in findings} >= {"multiple_answer_count", "similar_in_bank"}
    near_draft = review_question_set([multi, {**multi, "stem": "栈和队列在数据访问方式与入队出队顺序上有什么区别？"}])
    assert any(item["code"] == "similar_in_draft" for item in near_draft)


class _Auth:
    required = True

    def __init__(self, principals):
        self.principals = principals

    def verify_token(self, token):
        return self.principals.get(token)


def test_quality_api_is_private_and_publication_rechecks_server_side(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    owner_id, other_id, student_id, course_id, draft_id = (uuid4() for _ in range(5))
    with sessions.begin() as session:
        session.add_all([
            User(id=owner_id, username="teacher_owner", display_name="Owner", role="teacher", password_hash="x"),
            User(id=other_id, username="teacher_other", display_name="Other", role="teacher", password_hash="x"),
            User(id=student_id, username="student_q", display_name="Student", role="student", password_hash="x"),
            Course(id=course_id, title="数据结构", code="DSA-QA", owner_id=owner_id),
        ])
        session.flush()
        session.add(TeachingDraft(id=draft_id, course_id=course_id, creator_id=owner_id,
                                  draft_type="question_set", title="树题目", content="教师草稿",
                                  questions=[_question("二叉树先序遍历首先访问哪个子树？", "C")],
                                  source_context={}, status="confirmed"))

    service = TeachingDraftService(sessions)
    monkeypatch.setattr(main_module, "teaching_drafts", service)
    monkeypatch.setattr(main_module, "auth", _Auth({
        "owner": Principal(id=str(owner_id), username="teacher_owner", display_name="Owner", role="teacher"),
        "other": Principal(id=str(other_id), username="teacher_other", display_name="Other", role="teacher"),
        "student": Principal(id=str(student_id), username="student_q", display_name="Student", role="student"),
    }))
    client = TestClient(main_module.app)
    path = f"/api/v1/teaching-drafts/{draft_id}/quality-check"
    assert client.get(path, headers={"Authorization": "Bearer student"}).status_code == 403
    assert client.get(path, headers={"Authorization": "Bearer other"}).status_code == 404
    response = client.get(path, headers={"Authorization": "Bearer owner"})
    assert response.status_code == 200
    assert response.json()["error_count"] == 1
    assert response.json()["findings"][0]["code"] == "answer_not_in_options"
    with pytest.raises(ValueError, match="参考答案未对应现有选项"):
        service.publish_questions(draft_id, actor_id=owner_id, role="teacher")
    with sessions.begin() as session:
        assert session.query(QuestionBankItem).count() == 0
        assert session.get(TeachingDraft, draft_id).status == "confirmed"

    service.update(draft_id, actor_id=owner_id, role="teacher",
                   data={"questions": [_question("二叉树先序遍历首先访问哪个子树？", "A")]})
    service.update(draft_id, actor_id=owner_id, role="teacher", data={"status": "confirmed"})
    published, question_ids = service.publish_questions(draft_id, actor_id=owner_id, role="teacher")
    assert published["status"] == "published" and len(question_ids) == 1
    with sessions.begin() as session:
        assert session.query(QuestionBankItem).count() == 1
