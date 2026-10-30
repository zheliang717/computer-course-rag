"""Assignment commentary stays draft until teacher confirmation and safe publication."""

from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.assessment import AssessmentService
from app.assignment_reviews import AssignmentReviewService
from app.auth import Principal
from app.database import Base
from app.models import (
    Assignment, AssignmentQuestion, AssignmentSubmission, AuditLog, Course, CourseEnrollment,
    QuestionBankItem, SubmissionReview, TeachingDraft, User,
)
from app.teaching_drafts import TeachingDraftService


class _Auth:
    required = True

    def __init__(self, principals):
        self.principals = principals

    def verify_token(self, token):
        return self.principals.get(token)


class _Admin:
    def __init__(self):
        self.audits = []

    def add_audit(self, **kwargs):
        self.audits.append(kwargs)


class _Usage:
    def __init__(self):
        self.reservations = []
        self.finishes = []
        self.quota_error = None

    def reserve(self, **kwargs):
        self.reservations.append(kwargs)
        if self.quota_error is not None:
            raise self.quota_error
        return uuid4()

    def finish(self, reservation_id, **kwargs):
        self.finishes.append((reservation_id, kwargs))


def test_review_draft_uses_anonymous_stats_and_only_submitters_see_published_review(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    teacher_id, outsider_id, student_id, other_student_id = (uuid4() for _ in range(4))
    course_id, assignment_id, choice_id, written_id = (uuid4() for _ in range(4))
    pending_id = uuid4()
    with sessions.begin() as session:
        session.add_all([
            User(id=teacher_id, username="review_teacher", display_name="Teacher", role="teacher", password_hash="x"),
            User(id=outsider_id, username="review_outsider", display_name="Outsider", role="teacher", password_hash="x"),
            User(id=student_id, username="review_student", display_name="Alice", role="student", password_hash="x"),
            User(id=other_student_id, username="unsubmitted", display_name="Bob", role="student", password_hash="x"),
            Course(id=course_id, title="数据结构", code="DSA-REVIEW", owner_id=teacher_id, status="published"),
        ])
        session.flush()
        session.add_all([
            CourseEnrollment(course_id=course_id, user_id=student_id, status="active"),
            CourseEnrollment(course_id=course_id, user_id=other_student_id, status="active"),
            QuestionBankItem(id=choice_id, course_id=course_id, question_type="single_choice",
                             stem="先序遍历先访问什么？", options=["A. 根", "B. 右子树"],
                             correct_answer="A", explanation="先访问根。", knowledge_point="树遍历"),
            QuestionBankItem(id=written_id, course_id=course_id, question_type="short_answer",
                             stem="解释递归终止条件。", options=[], correct_answer="需要基础情况。",
                             explanation="递归必须能收敛。", knowledge_point="递归"),
            Assignment(id=assignment_id, course_id=course_id, creator_id=teacher_id,
                       title="树与递归作业", status="published"),
        ])
        session.flush()
        session.add_all([
            AssignmentQuestion(assignment_id=assignment_id, question_id=choice_id, position=1, points=10),
            AssignmentQuestion(assignment_id=assignment_id, question_id=written_id, position=2, points=10),
            AssignmentSubmission(id=pending_id, assignment_id=assignment_id, student_id=student_id,
                                 answers={str(choice_id): "A. 根", str(written_id): "需要终止条件。"},
                                 score=10, max_score=20, status="pending_review"),
        ])

    service, drafts, admin = AssignmentReviewService(sessions), TeachingDraftService(sessions), _Admin()
    assessment = AssessmentService(sessions)
    monkeypatch.setattr(main_module, "assignment_reviews", service)
    monkeypatch.setattr(main_module, "teaching_drafts", drafts)
    monkeypatch.setattr(main_module, "assessment", assessment)
    monkeypatch.setattr(main_module, "admin_service", admin)
    monkeypatch.setattr(main_module, "settings", main_module.settings.model_copy(update={"llm_provider": "offline"}))
    monkeypatch.setattr(main_module, "auth", _Auth({
        "teacher": Principal(id=str(teacher_id), username="review_teacher", display_name="Teacher", role="teacher"),
        "outsider": Principal(id=str(outsider_id), username="review_outsider", display_name="Outsider", role="teacher"),
        "student": Principal(id=str(student_id), username="review_student", display_name="Alice", role="student"),
        "unsubmitted": Principal(id=str(other_student_id), username="unsubmitted", display_name="Bob", role="student"),
    }))
    client = TestClient(main_module.app)
    assignment_path = f"/api/v1/assignments/{assignment_id}"
    pending_student_view = client.get(assignment_path, headers={"Authorization": "Bearer student"})
    assert pending_student_view.status_code == 200
    assert pending_student_view.json()["submission_status"] == "pending_review"
    assert pending_student_view.json()["score"] is None
    assert pending_student_view.json()["submitted_answers"][str(written_id)] == "需要终止条件。"
    assert pending_student_view.json()["questions"][0]["correct_answer"] is None
    assert client.get(assignment_path, headers={"Authorization": "Bearer unsubmitted"}).json()["submitted_answers"] is None
    assert client.post(f"{assignment_path}/submit", headers={"Authorization": "Bearer student"},
                       json={"answers": {str(choice_id): "B. 右子树"}}).status_code == 409
    with sessions.begin() as session:
        assert session.get(AssignmentSubmission, pending_id).answers[str(choice_id)] == "A. 根"
    path = f"/api/v1/assignments/{assignment_id}/review-drafts"
    assert client.post(path, headers={"Authorization": "Bearer student"}, json={}).status_code == 403
    assert client.post(path, headers={"Authorization": "Bearer outsider"}, json={}).status_code == 404
    created = client.post(path, headers={"Authorization": "Bearer teacher"}, json={})
    assert created.status_code == 201, created.text
    first = created.json()
    assert first["status"] == "draft" and first["draft_type"] == "review"
    assert "Alice" not in first["content"] and "Bob" not in first["content"]
    assert first["source_context"]["pending_review_count"] == 1
    assert service.snapshot(assignment_id, actor_id=teacher_id, role="teacher")["questions"][0]["correct_count"] == 1
    review_path = f"/api/v1/assignments/{assignment_id}/review"
    assert client.get(review_path, headers={"Authorization": "Bearer student"}).status_code == 404
    publish_path = f"/api/v1/teaching-drafts/{first['id']}/publish-review"
    assert client.post(publish_path, headers={"Authorization": "Bearer teacher"}).status_code == 409
    assert client.patch(f"/api/v1/teaching-drafts/{first['id']}", headers={"Authorization": "Bearer teacher"},
                        json={"status": "confirmed"}).status_code == 200
    still_pending = client.post(publish_path, headers={"Authorization": "Bearer teacher"})
    assert still_pending.status_code == 409 and "待批改" in still_pending.text

    def fail_audit_insert(_connection, _cursor, statement, _parameters, _context, _executemany):
        if "insert into audit_logs" in statement.lower():
            raise RuntimeError("audit write failed")

    grade_path = f"/api/v1/submissions/{pending_id}/grade"
    assert client.patch(grade_path, headers={"Authorization": "Bearer student"},
                        json={"score": 18}).status_code == 403
    assert client.patch(grade_path, headers={"Authorization": "Bearer outsider"},
                        json={"score": 18}).status_code == 404
    assert client.patch(grade_path, headers={"Authorization": "Bearer teacher"},
                        json={"score": 21}).status_code == 422
    event.listen(engine, "before_cursor_execute", fail_audit_insert)
    try:
        with pytest.raises(RuntimeError, match="audit write failed"):
            client.patch(grade_path, headers={"Authorization": "Bearer teacher"},
                         json={"score": 18, "feedback": "需说明基础情况。"})
    finally:
        event.remove(engine, "before_cursor_execute", fail_audit_insert)
    with sessions.begin() as session:
        assert session.get(AssignmentSubmission, pending_id).status == "pending_review"
        assert session.scalar(select(SubmissionReview).where(SubmissionReview.submission_id == pending_id)) is None
        assert session.scalars(select(AuditLog).where(AuditLog.action == "grade")).all() == []
    graded = client.patch(grade_path, headers={"Authorization": "Bearer teacher"},
                          json={"score": 18, "feedback": "需说明基础情况。"})
    assert graded.status_code == 200
    with sessions.begin() as session:
        grade_audits = session.scalars(select(AuditLog).where(AuditLog.action == "grade")).all()
        assert len(grade_audits) == 1
        assert grade_audits[0].actor_id == teacher_id
        assert grade_audits[0].resource_id == str(pending_id)
        assert grade_audits[0].detail["previous_status"] == "pending_review"
        assert grade_audits[0].detail["score"] == 18
    graded_student_view = client.get(assignment_path, headers={"Authorization": "Bearer student"})
    assert graded_student_view.status_code == 200
    assert graded_student_view.json()["submission_status"] == "graded"
    assert graded_student_view.json()["score"] == 18
    assert graded_student_view.json()["teacher_feedback"] == "需说明基础情况。"
    assert graded_student_view.json()["questions"][0]["correct_answer"] == "A"
    event.listen(engine, "before_cursor_execute", fail_audit_insert)
    try:
        with pytest.raises(RuntimeError, match="audit write failed"):
            client.patch(grade_path, headers={"Authorization": "Bearer teacher"},
                         json={"score": 19, "feedback": "更新评语"})
    finally:
        event.remove(engine, "before_cursor_execute", fail_audit_insert)
    with sessions.begin() as session:
        assert session.scalar(select(SubmissionReview).where(SubmissionReview.submission_id == pending_id)).score == 18
        assert len(session.scalars(select(AuditLog).where(AuditLog.action == "grade")).all()) == 1
    stale = client.post(publish_path, headers={"Authorization": "Bearer teacher"})
    assert stale.status_code == 409 and "已变化" in stale.text
    fresh = client.post(path, headers={"Authorization": "Bearer teacher"}, json={})
    assert fresh.status_code == 201
    fresh_id = fresh.json()["id"]
    assert fresh.json()["source_context"]["graded_count"] == 1
    assert client.patch(f"/api/v1/teaching-drafts/{fresh_id}", headers={"Authorization": "Bearer teacher"},
                        json={"status": "confirmed"}).status_code == 200
    event.listen(engine, "before_cursor_execute", fail_audit_insert)
    try:
        with pytest.raises(RuntimeError, match="audit write failed"):
            client.post(f"/api/v1/teaching-drafts/{fresh_id}/publish-review",
                        headers={"Authorization": "Bearer teacher"})
    finally:
        event.remove(engine, "before_cursor_execute", fail_audit_insert)
    with sessions.begin() as session:
        assert session.get(Assignment, assignment_id).published_review_draft_id is None
        assert session.get(TeachingDraft, UUID(fresh_id)).status == "confirmed"
        assert session.scalars(select(AuditLog).where(AuditLog.action == "publish_assignment_review")).all() == []
    published = client.post(f"/api/v1/teaching-drafts/{fresh_id}/publish-review",
                            headers={"Authorization": "Bearer teacher"})
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert client.get(review_path, headers={"Authorization": "Bearer unsubmitted"}).status_code == 404
    assert client.get(review_path, headers={"Authorization": "Bearer outsider"}).status_code == 404
    visible = client.get(review_path, headers={"Authorization": "Bearer student"})
    assert visible.status_code == 200 and visible.json()["draft_id"] == fresh_id
    assert client.patch(f"/api/v1/teaching-drafts/{fresh_id}", headers={"Authorization": "Bearer teacher"},
                        json={"content": "不应再修改"}).status_code == 409
    with sessions.begin() as session:
        session.add(AssignmentSubmission(assignment_id=assignment_id, student_id=other_student_id,
                                         answers={str(choice_id): "B. 右子树", str(written_id): "递归继续。"},
                                         score=0, max_score=20, status="graded"))
    assert client.get(review_path, headers={"Authorization": "Bearer student"}).status_code == 404
    teacher_view = client.get(review_path, headers={"Authorization": "Bearer teacher"})
    assert teacher_view.status_code == 200 and teacher_view.json()["stale"] is True
    replacement = client.post(path, headers={"Authorization": "Bearer teacher"}, json={})
    assert replacement.status_code == 201
    replacement_id = replacement.json()["id"]
    assert client.patch(f"/api/v1/teaching-drafts/{replacement_id}", headers={"Authorization": "Bearer teacher"},
                        json={"status": "confirmed"}).status_code == 200
    assert client.post(f"/api/v1/teaching-drafts/{replacement_id}/publish-review",
                       headers={"Authorization": "Bearer teacher"}).status_code == 200
    assert client.get(review_path, headers={"Authorization": "Bearer student"}).json()["draft_id"] == replacement_id
    with sessions.begin() as session:
        assert session.get(Assignment, assignment_id).published_review_draft_id == session.get(TeachingDraft, UUID(replacement_id)).id
        assert session.get(TeachingDraft, UUID(fresh_id)).status == "archived"
        publish_audits = session.scalars(select(AuditLog).where(
            AuditLog.action == "publish_assignment_review",
        ).order_by(AuditLog.created_at)).all()
        assert len(publish_audits) == 2
        assert publish_audits[0].resource_id == str(assignment_id)
        assert publish_audits[0].detail["draft_id"] == fresh_id
        assert publish_audits[1].detail["replaced_draft_id"] == fresh_id


def test_online_review_requires_consent_and_excludes_student_identity_and_answers(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    teacher_id, student_id, course_id, assignment_id, question_id = (uuid4() for _ in range(5))
    with sessions.begin() as session:
        session.add_all([
            User(id=teacher_id, username="teacher-online", display_name="Teacher", role="teacher", password_hash="x"),
            User(id=student_id, username="student-online", display_name="SENSITIVE-STUDENT-NAME", role="student", password_hash="x"),
            Course(id=course_id, title="计算机网络", code="NET-REVIEW", owner_id=teacher_id, status="published"),
        ])
        session.flush()
        session.add_all([
            CourseEnrollment(course_id=course_id, user_id=student_id, status="active"),
            QuestionBankItem(id=question_id, course_id=course_id, question_type="single_choice",
                             stem="TCP 如何确认接收？", options=["A. ACK", "B. DNS"],
                             correct_answer="A", explanation="使用确认号。", knowledge_point="TCP"),
            Assignment(id=assignment_id, course_id=course_id, creator_id=teacher_id,
                       title="网络作业", status="published"),
        ])
        session.flush()
        session.add_all([
            AssignmentQuestion(assignment_id=assignment_id, question_id=question_id, position=1, points=10),
            AssignmentSubmission(assignment_id=assignment_id, student_id=student_id,
                                 answers={str(question_id): "SENSITIVE-INDIVIDUAL-ANSWER"},
                                 score=0, max_score=10, status="graded"),
        ])

    class _Generator:
        def __init__(self):
            self.prompts = []
            self.failure = None

        def generate(self, prompt, citations, *, grounded, task):
            self.prompts.append(prompt)
            assert citations == [] and grounded is False and task == "assignment_review"
            if self.failure is not None:
                raise self.failure
            return "## 作业讲评草稿\n\n请教师核对知识点和答题思路后再发布。"

    from app.model_usage import ModelUsageService
    from app.models import ModelQuota, ModelUsageLog
    from sqlalchemy import func
    class RecordingUsage(ModelUsageService):
        quota_error = None
        def reserve(self, **kwargs):
            if self.quota_error: raise self.quota_error
            return super().reserve(**kwargs)
        @property
        def finishes(self):
            with sessions() as s:
                return [(row.id, {"successful":row.successful,"error_type":row.error_type}) for row in
                    s.scalars(select(ModelUsageLog).order_by(ModelUsageLog.created_at,ModelUsageLog.id))
                    if row.error_type != "pending"]
    with sessions.begin() as s:s.add(ModelQuota(role="teacher",daily_limit=10))
    def audit_count():
        with sessions() as s:return s.scalar(select(func.count(AuditLog.id)).where(AuditLog.action=="generate_assignment_review_draft"))
    generator, usage, admin = _Generator(), RecordingUsage(sessions), _Admin()
    monkeypatch.setattr(main_module, "assignment_reviews", AssignmentReviewService(sessions))
    monkeypatch.setattr(main_module, "teaching_drafts", TeachingDraftService(sessions))
    monkeypatch.setattr(main_module, "admin_service", admin)
    monkeypatch.setattr(main_module, "model_usage", usage)
    monkeypatch.setattr(main_module, "generator", generator)
    monkeypatch.setattr(main_module, "settings", main_module.settings.model_copy(update={"llm_provider": "compatible"}))
    monkeypatch.setattr(main_module, "auth", _Auth({
        "teacher": Principal(id=str(teacher_id), username="teacher-online", display_name="Teacher", role="teacher"),
    }))
    client = TestClient(main_module.app)
    path = f"/api/v1/assignments/{assignment_id}/review-drafts"
    refused = client.post(path, headers={"Authorization": "Bearer teacher"}, json={})
    assert refused.status_code == 409 and generator.prompts == []
    accepted = client.post(path, headers={"Authorization": "Bearer teacher"},
                           json={"confirm_external_analysis": True, "include_student_answers": False})
    assert accepted.status_code == 201, accepted.text
    assert len(generator.prompts) == 1
    assert "SENSITIVE-STUDENT-NAME" not in generator.prompts[0]
    assert "SENSITIVE-INDIVIDUAL-ANSWER" not in generator.prompts[0]
    assert "TCP 如何确认接收？" in generator.prompts[0]
    assert accepted.json()["status"] == "draft"
    assert "SENSITIVE-STUDENT-NAME" not in str(accepted.json()["source_context"])
    assert usage.finishes[-1][1]["successful"] is True

    generator.failure = httpx.ReadTimeout("model timed out")
    timed_out = client.post(path, headers={"Authorization": "Bearer teacher"},
                            json={"confirm_external_analysis": True, "include_student_answers": False})
    assert timed_out.status_code == 504 and "未创建或发布" in timed_out.json()["detail"]
    assert usage.finishes[-1][1]["successful"] is False
    assert usage.finishes[-1][1]["error_type"] == "ReadTimeout"
    assert audit_count() == 1
    with sessions.begin() as session:
        assert session.query(TeachingDraft).count() == 1

    generator.failure = None
    generator.generate = lambda *args, **kwargs: "invalid"
    invalid = client.post(path, headers={"Authorization": "Bearer teacher"},
                          json={"confirm_external_analysis": True, "include_student_answers": False})
    assert invalid.status_code == 502
    assert usage.finishes[-1][1]["successful"] is False
    assert usage.finishes[-1][1]["error_type"] == "RuntimeError"
    assert audit_count() == 1
    with sessions.begin() as session:
        assert session.query(TeachingDraft).count() == 1
        assert session.get(TeachingDraft, UUID(accepted.json()["id"])).status == "draft"
        assert session.get(Assignment, assignment_id).published_review_draft_id is None

    usage.quota_error = PermissionError("今日模型额度已用完")
    prompts_before = len(generator.prompts)
    quota_denied = client.post(path, headers={"Authorization": "Bearer teacher"},
                               json={"confirm_external_analysis": True, "include_student_answers": False})
    assert quota_denied.status_code == 429
    assert len(generator.prompts) == prompts_before
    assert audit_count() == 1
    assert len(usage.finishes) == 3
    with sessions.begin() as session:
        assert session.query(TeachingDraft).count() == 1

    local = client.post(path, headers={"Authorization": "Bearer teacher"}, json={"local_only": True})
    assert local.status_code == 201, local.text
    assert local.json()["source_context"]["model"] == "local-statistics"
    assert "当前未使用在线模型" in local.json()["content"]
    assert len(generator.prompts) == prompts_before
    assert len(usage.finishes) == 3
    assert audit_count() == 2
