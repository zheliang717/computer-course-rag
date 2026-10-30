"""Study plans use only course-scoped records and follow real task completion."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.auth import Principal
from app.database import Base
from app.models import (
    Assignment, AssignmentSubmission, Course, CourseEnrollment, CourseSection,
    CourseSession, QuestionBankItem, User, WrongQuestion,
)
from app.study_plans import StudyPlanService
from app.assessment import AssessmentService


class _TestAuth:
    required = True

    def __init__(self, principals):
        self.principals = principals

    def verify_token(self, token):
        return self.principals.get(token)


def test_study_plan_is_private_actionable_and_tracks_actual_work(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    student_id, outsider_id, teacher_id = uuid4(), uuid4(), uuid4()
    course_id, section_id, assignment_id, question_id = uuid4(), uuid4(), uuid4(), uuid4()
    with sessions.begin() as session:
        session.add_all([
            User(id=student_id, username="student_a", display_name="Student A", role="student", password_hash="x"),
            User(id=outsider_id, username="student_b", display_name="Student B", role="student", password_hash="x"),
            User(id=teacher_id, username="teacher_a", display_name="Teacher", role="teacher", password_hash="x"),
            Course(id=course_id, title="数据结构", code="DSA-PLAN", status="published", owner_id=teacher_id),
        ])
        session.flush()
        session.add_all([
            CourseEnrollment(course_id=course_id, user_id=student_id, status="active"),
            CourseSection(id=section_id, course_id=course_id, title="树与二叉树", position=1),
            CourseSession(course_id=course_id, section_id=section_id, title="二叉树遍历",
                          session_date=datetime.now(timezone.utc) + timedelta(days=2), completed=False),
            Assignment(id=assignment_id, course_id=course_id, title="树结构作业", status="published",
                       due_at=datetime.now(timezone.utc) + timedelta(days=3)),
            QuestionBankItem(id=question_id, course_id=course_id, section_id=section_id,
                             stem="什么是二叉树？", correct_answer="树", options=[]),
        ])
        session.flush()
        session.add(WrongQuestion(student_id=student_id, question_id=question_id, mastered=False))

    service = StudyPlanService(sessions)
    assert service.create(student_id=outsider_id, course_id=course_id) is None
    plan = service.create(student_id=student_id, course_id=course_id)
    assert plan is not None
    assert {item["kind"] for item in plan["items"]} == {"assignment", "wrong_question", "section_preview"}
    assert plan["actionable_count"] == 2 and plan["completed_count"] == 0
    assert service.list_current(student_id=outsider_id) == []

    monkeypatch.setattr(main_module, "study_plans", service)
    monkeypatch.setattr(main_module, "auth", _TestAuth({
        "student": Principal(id=str(student_id), username="student_a", display_name="Student A", role="student"),
        "outsider": Principal(id=str(outsider_id), username="student_b", display_name="Student B", role="student"),
        "teacher": Principal(id=str(teacher_id), username="teacher_a", display_name="Teacher", role="teacher"),
    }))
    client = TestClient(main_module.app)
    assert client.get("/api/v1/study-plans", headers={"Authorization": "Bearer teacher"}).status_code == 403
    assert client.get("/api/v1/study-plans", headers={"Authorization": "Bearer outsider"}).json() == []
    assert client.post("/api/v1/study-plans", headers={"Authorization": "Bearer outsider"},
                       json={"course_id": str(course_id)}).status_code == 404
    visible = client.get("/api/v1/study-plans", headers={"Authorization": "Bearer student"})
    assert visible.status_code == 200 and len(visible.json()) == 1

    with sessions.begin() as session:
        session.add(AssignmentSubmission(assignment_id=assignment_id, student_id=student_id,
                                         answers={}, score=10, max_score=10))
    AssessmentService(sessions).submit_practice_attempt(question_id, student_id=student_id, answer="树")
    AssessmentService(sessions).submit_practice_attempt(question_id, student_id=student_id, answer="树")
    updated = service.list_current(student_id=student_id)[0]
    assert updated["completed_count"] == updated["actionable_count"] == 2
    assert all(item["completed"] is True for item in updated["items"] if item["completed"] is not None)

    regenerated = service.create(student_id=student_id, course_id=course_id)
    assert regenerated is not None and regenerated["id"] != plan["id"]
    assert len(service.list_current(student_id=student_id)) == 1
