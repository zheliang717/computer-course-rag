"""Question and course notice management with real SQL paging and role boundaries."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.assessment import AssessmentService
from app.admin import AdminService
from app.analytics import AnalyticsService
from app.auth import Principal
from app.catalog import KnowledgeCatalog
from app.database import Base
from app.history import PersistentHistory
from app.learning import LearningService
from app.moderation import QuestionModerationService
from app.models import Assignment, AssignmentQuestion, AuditLog, Course, CourseEnrollment, CourseKnowledgeBase, Document, KnowledgeBase, QuestionRecord, User


class _Auth:
    required = True

    def __init__(self, identities):
        self.identities = identities

    def verify_token(self, token):
        return self.identities.get(token)


def _h(name):
    return {"Authorization": f"Bearer {name}"}


def _app(monkeypatch, sessions=None):
    if sessions is None:
        engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
    ids = {name: uuid4() for name in ("teacher", "other", "student", "admin")}
    course_ids = [uuid4(), uuid4()]
    with sessions.begin() as session:
        for name, role in (("teacher", "teacher"), ("other", "teacher"), ("student", "student"), ("admin", "admin")):
            session.add(User(id=ids[name], username=name, display_name=name, role=role, password_hash="x"))
        session.flush()
        session.add_all([
            Course(id=course_ids[0], title="Course A", code="TEST-A", status="published", owner_id=ids["teacher"]),
            Course(id=course_ids[1], title="Course B", code="TEST-B", status="published", owner_id=ids["other"]),
        ])
        session.flush()
        session.add(CourseEnrollment(course_id=course_ids[0], user_id=ids["student"], status="active"))
    principals = {
        name: Principal(id=str(ids[name]), username=name, display_name=name,
                        role="teacher" if name in {"teacher", "other"} else name)
        for name in ids
    }
    monkeypatch.setattr(main_module, "auth", _Auth(principals))
    monkeypatch.setattr(main_module, "assessment", AssessmentService(sessions))
    monkeypatch.setattr(main_module, "learning", LearningService(sessions))
    return TestClient(main_module.app), sessions, ids, course_ids


def _question(course_id, stem):
    return {"course_id": str(course_id), "question_type": "true_false", "stem": stem,
            "options": ["正确", "错误"], "correct_answer": "正确", "difficulty": 2}


def test_question_crud_pagination_access_and_used_guard(monkeypatch):
    client, sessions, ids, (own_course, other_course) = _app(monkeypatch)
    created = []
    for index in range(3):
        response = client.post("/api/v1/questions", headers=_h("teacher"),
                               json=_question(own_course, f"演示算法题 {index}"))
        assert response.status_code == 201, response.text
        created.append(response.json()["id"])
    foreign = client.post("/api/v1/questions", headers=_h("other"),
                          json=_question(other_course, "其他课程题目"))
    assert foreign.status_code == 201

    first = client.get("/api/v1/questions/page?page=1&page_size=2&keyword=演示", headers=_h("teacher"))
    second = client.get("/api/v1/questions/page?page=2&page_size=2&keyword=演示", headers=_h("teacher"))
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 3
    assert len(first.json()["items"]) == 2 and len(second.json()["items"]) == 1
    assert {item["id"] for item in first.json()["items"]}.isdisjoint(
        {item["id"] for item in second.json()["items"]})
    assert client.get("/api/v1/questions/page?question_type=fill_blank", headers=_h("teacher")).json()["total"] == 0
    assert client.get("/api/v1/questions/page?page=0", headers=_h("teacher")).status_code == 422
    assert client.get("/api/v1/questions/page?page_size=51", headers=_h("teacher")).status_code == 422
    assert len(client.get("/api/v1/questions", headers=_h("teacher")).json()) == 3  # legacy endpoint

    student_page = client.get("/api/v1/questions/page", headers=_h("student")).json()
    assert student_page["total"] == 3
    assert all(item["correct_answer"] is None for item in student_page["items"])
    assert client.get(f"/api/v1/questions/{foreign.json()['id']}", headers=_h("student")).status_code == 404
    assert client.patch(f"/api/v1/questions/{created[0]}", headers=_h("student"), json={"stem": "Denied"}).status_code == 403
    assert client.patch(f"/api/v1/questions/{created[0]}", headers=_h("other"), json={"stem": "Denied"}).status_code == 404
    assert client.delete(f"/api/v1/questions/{created[0]}", headers=_h("other")).status_code == 404

    changed = client.patch(f"/api/v1/questions/{created[0]}", headers=_h("teacher"),
                           json={"stem": "演示算法题 已更新", "explanation": "测试解析"})
    assert changed.status_code == 200 and changed.json()["stem"] == "演示算法题 已更新"
    with sessions.begin() as session:
        assignment = Assignment(course_id=own_course, title="历史作业", creator_id=ids["teacher"])
        session.add(assignment)
        session.flush()
        session.add(AssignmentQuestion(assignment_id=assignment.id, question_id=UUID(created[0]), position=1))
    assert client.patch(f"/api/v1/questions/{created[0]}", headers=_h("teacher"), json={"stem": "不可变更"}).status_code == 409
    assert client.delete(f"/api/v1/questions/{created[0]}", headers=_h("teacher")).status_code == 409
    assert client.get(f"/api/v1/questions/{created[0]}", headers=_h("teacher")).json()["stem"] == "演示算法题 已更新"
    assert client.delete(f"/api/v1/questions/{created[1]}", headers=_h("teacher")).status_code == 204
    assert client.get(f"/api/v1/questions/{created[1]}", headers=_h("teacher")).status_code == 404
    with sessions() as session:
        actions = set(session.scalars(select(AuditLog.action)).all())
        assert {"update_question", "delete_question"} <= actions


def test_course_announcement_crud_pagination_and_legacy(monkeypatch):
    client, sessions, _, (own_course, other_course) = _app(monkeypatch)
    root = f"/api/v1/courses/{own_course}/announcements"
    ids = []
    for index in range(7):
        response = client.post(root, headers=_h("teacher"),
                               json={"title": f"测试公告 {index}", "content": "仅供功能测试"})
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    first = client.get(f"{root}/page?page=1&page_size=5", headers=_h("student"))
    second = client.get(f"{root}/page?page=2&page_size=5", headers=_h("student"))
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == 7 and len(first.json()["items"]) == 5
    assert len(second.json()["items"]) == 2
    assert len(client.get(root, headers=_h("student")).json()) == 7
    assert client.get(f"{root}/page?page_size=51", headers=_h("student")).status_code == 422
    assert client.get(f"/api/v1/courses/{other_course}/announcements/page", headers=_h("student")).status_code == 404
    assert client.get(f"{root}/{ids[0]}", headers=_h("student")).status_code == 200
    assert client.put(f"{root}/{ids[0]}", headers=_h("student"), json={"title": "Denied", "content": "x"}).status_code == 403
    assert client.put(f"{root}/{ids[0]}", headers=_h("other"), json={"title": "Denied", "content": "x"}).status_code == 404
    changed = client.put(f"{root}/{ids[0]}", headers=_h("teacher"),
                         json={"title": "测试公告 已更新", "content": "更新内容"})
    assert changed.status_code == 200 and changed.json()["title"] == "测试公告 已更新"
    assert client.delete(f"{root}/{ids[0]}", headers=_h("teacher")).status_code == 204
    assert client.get(f"{root}/{ids[0]}", headers=_h("student")).status_code == 404
    assert client.get(f"{root}/page", headers=_h("teacher")).json()["total"] == 6
    with sessions() as session:
        actions = set(session.scalars(select(AuditLog.action)).all())
        assert {"publish_course_announcement", "update_course_announcement", "delete_course_announcement"} <= actions


def test_paged_admin_records_include_older_rows_and_validate_access(monkeypatch):
    client, sessions, ids, _ = _app(monkeypatch)
    monkeypatch.setattr(main_module, "admin_service", AdminService(sessions))
    with sessions.begin() as session:
        session.get(User, ids["other"]).active = False
        session.add_all([AuditLog(actor_id=ids["admin"], actor_name="admin", action="test",
                                 resource_type="test", detail={"index": index}) for index in range(61)])
    first = client.get("/api/v1/paged/audits?page=1&page_size=10", headers=_h("admin"))
    last = client.get("/api/v1/paged/audits?page=7&page_size=10", headers=_h("admin"))
    assert first.status_code == last.status_code == 200
    assert first.json()["total"] == last.json()["total"] == 61
    assert len(first.json()["items"]) == 10 and len(last.json()["items"]) == 1
    assert first.json()["items"][0]["id"] != last.json()["items"][0]["id"]
    users = client.get("/api/v1/paged/users?inactive_only=true", headers=_h("admin")).json()
    assert users["total"] == 1 and users["items"][0]["id"] == str(ids["other"])
    assert "password_hash" not in users["items"][0]
    for name in ("student", "teacher"):
        for resource in ("users", "audits", "evaluations", "logins", "requests", "model-calls"):
            assert client.get(f"/api/v1/paged/{resource}", headers=_h(name)).status_code == 403
    assert client.get("/api/v1/paged/audits?page=0", headers=_h("admin")).status_code == 422
    assert client.get("/api/v1/paged/audits?page_size=51", headers=_h("admin")).status_code == 422
    assert client.get("/api/v1/paged/unknown", headers=_h("admin")).status_code == 422


def test_paged_course_documents_history_and_reviews_keep_scope(monkeypatch, postgres_sessions):
    client, sessions, ids, (own_course, other_course) = _app(monkeypatch, postgres_sessions)
    own_base, other_base = uuid4(), uuid4()
    with sessions.begin() as session:
        session.add_all([KnowledgeBase(id=own_base, name="Own", course="Own"),
                         KnowledgeBase(id=other_base, name="Other", course="Other")])
        session.flush()
        session.add_all([CourseKnowledgeBase(course_id=own_course, knowledge_base_id=own_base),
                         CourseKnowledgeBase(course_id=other_course, knowledge_base_id=other_base)])
        for index in range(3):
            session.add(Document(knowledge_base_id=own_base, filename=f"Book {index}",
                                 publication_status="draft" if index == 0 else "published"))
            session.add(QuestionRecord(knowledge_base_id=own_base, user_id=ids["student"], question=f"My question {index}",
                                       answer="answer", message="ok", model="offline", favorite=index == 0))
        session.add(QuestionRecord(knowledge_base_id=other_base, user_id=ids["other"], question="Private question",
                                   answer="answer", message="ok", model="offline"))
        session.add_all([Assignment(course_id=own_course, title="Published", status="published"),
                         Assignment(course_id=own_course, title="Draft", status="draft"),
                         Assignment(course_id=other_course, title="Foreign", status="published")])
    monkeypatch.setattr(main_module, "catalog", KnowledgeCatalog(sessions))
    monkeypatch.setattr(main_module, "analytics", AnalyticsService(sessions))
    monkeypatch.setattr(main_module, "history", PersistentHistory(sessions))
    monkeypatch.setattr(main_module, "moderation", QuestionModerationService(sessions, None))
    documents = client.get(f"/api/v1/paged/documents?scope_id={own_base}&page_size=1", headers=_h("student"))
    assert documents.status_code == 200 and documents.json()["total"] == 2
    assert len(documents.json()["items"]) == 1 and documents.json()["items"][0]["publication_status"] == "published"
    assert client.get(f"/api/v1/paged/documents?scope_id={other_base}", headers=_h("student")).status_code == 404
    assert client.get("/api/v1/paged/documents", headers=_h("student")).status_code == 422
    own_history = client.get("/api/v1/paged/history?page_size=2", headers=_h("student")).json()
    assert own_history["total"] == 3 and len(own_history["items"]) == 2
    assert all(item["question"].startswith("My question") for item in own_history["items"])
    assert client.get("/api/v1/paged/history?favorites_only=true", headers=_h("student")).json()["total"] == 1
    assert client.get("/api/v1/paged/history", headers=_h("teacher")).json()["total"] == 0
    assert client.get("/api/v1/paged/reviews", headers=_h("teacher")).json()["total"] == 3
    assert client.get("/api/v1/paged/reviews", headers=_h("student")).status_code == 403
    assert client.get("/api/v1/paged/assignments", headers=_h("student")).json()["total"] == 1
    assert client.get("/api/v1/paged/assignments", headers=_h("teacher")).json()["total"] == 2
    assert client.get("/api/v1/paged/courses", headers=_h("student")).json()["total"] == 1
    assert client.get(f"/api/v1/paged/members?scope_id={own_course}", headers=_h("student")).status_code == 403
    assert client.get(f"/api/v1/paged/members?scope_id={other_course}", headers=_h("teacher")).status_code == 404
