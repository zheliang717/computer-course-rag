"""Destructive-but-self-cleaning business acceptance flow for the local Docker stack."""
import os
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import psycopg
import pytest
from sqlalchemy.engine import make_url


pytestmark = pytest.mark.skipif(os.getenv("LIVE_API_TESTS") != "1", reason="requires the live Docker stack")
BASE_URL = os.getenv("LIVE_API_URL", "http://127.0.0.1:8000")
DATABASE_URL = os.getenv("LIVE_DATABASE_URL", "")
if os.getenv('LIVE_API_TESTS') == '1':
    if BASE_URL != 'http://127.0.0.1:18084' or not DATABASE_URL or make_url(DATABASE_URL).database != 'rag_today_dev_20261028':
        raise RuntimeError('Business tests require the explicit isolated API/database copy; live writes refused')
_LOGIN_CACHE: dict[str, dict[str, str]] = {}


def _login(client: httpx.Client, username: str, password: str) -> dict[str, str]:
    if username in _LOGIN_CACHE:
        return _LOGIN_CACHE[username]
    response = None
    for _ in range(30):
        try:
            response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
            if response.status_code == 429:
                time.sleep(min(int(response.headers.get("Retry-After", "1")), 60))
                continue
            if response.status_code != 502:
                break
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    assert response is not None
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    _LOGIN_CACHE[username] = headers
    return headers


def test_course_assignment_requires_teacher_publish_and_hides_draft_from_student() -> None:
    assignment_id = None
    with httpx.Client(base_url=BASE_URL, timeout=20) as client:
        teacher = _login(client, "teacher", "teacher123")
        student = _login(client, "student", "student123")
        teacher_courses = client.get("/api/v1/courses", headers=teacher).json()
        student_course_ids = {item["id"] for item in client.get("/api/v1/courses", headers=student).json()}
        questions = client.get("/api/v1/questions", headers=teacher).json()
        course = next(item for item in teacher_courses if item["id"] in student_course_ids
                      and any(question["course_id"] == item["id"] for question in questions))
        question = next(item for item in questions if item["course_id"] == course["id"])
        payload = {"course_id": course["id"], "title": f"课程作业草稿验收-{uuid4().hex[:8]}",
                   "question_ids": [question["id"]]}
        try:
            direct_publish = client.post("/api/v1/assignments", headers=teacher, json={**payload, "status": "published"})
            assert direct_publish.status_code == 422
            created = client.post("/api/v1/assignments", headers=teacher, json={**payload, "status": "draft"})
            assert created.status_code == 201, created.text
            assignment_id = created.json()["id"]
            assert created.json()["course_id"] == course["id"]
            assert created.json()["class_id"] is None
            assert client.get(f"/api/v1/assignments/{assignment_id}", headers=student).status_code == 404
            listed = client.get("/api/v1/assignments", headers=student).json()
            assert assignment_id not in {item["id"] for item in listed}
            published = client.patch(f"/api/v1/assignments/{assignment_id}/status", headers=teacher,
                                     json={"status": "published"})
            assert published.status_code == 200 and published.json()["status"] == "published"
            assert client.get(f"/api/v1/assignments/{assignment_id}", headers=student).status_code == 200
        finally:
            if assignment_id:
                with psycopg.connect(DATABASE_URL) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("DELETE FROM assignments WHERE id = %s AND title = %s",
                                       (assignment_id, payload["title"]))


def test_direct_course_membership_controls_student_access() -> None:
    username = f"course_accept_{uuid4().hex[:10]}"
    user_id = None
    with httpx.Client(base_url=BASE_URL, timeout=20) as client:
        admin = _login(client, "admin", "admin123")
        teacher = _login(client, "teacher", "teacher123")
        course = next(item for item in client.get("/api/v1/courses", headers=teacher).json()
                      if item["code"] == "DSA-2026")
        other_course = next(item for item in client.get("/api/v1/courses", headers=teacher).json()
                            if item["code"] == "OS-2026")
        own_base = client.get(f"/api/v1/courses/{course['id']}/knowledge-bases", headers=teacher).json()[0]["id"]
        other_base = client.get(f"/api/v1/courses/{other_course['id']}/knowledge-bases", headers=teacher).json()[0]["id"]
        other_document = client.get(f"/api/v1/knowledge-bases/{other_base}/documents", headers=teacher).json()[0]["id"]
        try:
            created = client.post("/api/v1/admin/users", headers=admin, json={
                "username": username, "display_name": "课程成员验收学生", "role": "student", "password": "Acceptance123!",
            })
            assert created.status_code == 201, created.text
            user_id = created.json()["id"]
            student = _login(client, username, "Acceptance123!")
            assert client.get("/api/v1/courses", headers=student).json() == []
            assert client.get("/api/v1/knowledge-bases", headers=student).json() == []
            assert client.post("/api/v1/questions/retrieve", headers=student, json={
                "question": "什么是虚拟内存？", "knowledge_base_id": other_base,
            }).status_code == 404
            assert client.get(f"/api/v1/courses/{course['id']}/members", headers=student).status_code == 403

            enrolled = client.post(f"/api/v1/courses/{course['id']}/members", headers=teacher,
                                   json={"username": username})
            assert enrolled.status_code == 201 and enrolled.json()["status"] == "active"
            assert {item["id"] for item in client.get("/api/v1/courses", headers=student).json()} == {course["id"]}
            plan = client.post("/api/v1/study-plans", headers=student, json={"course_id": course["id"]})
            assert plan.status_code == 201, plan.text
            assert plan.json()["course_id"] == course["id"] and plan.json()["items"]
            assert {item["id"] for item in client.get("/api/v1/study-plans", headers=student).json()} == {plan.json()["id"]}
            assert client.get("/api/v1/study-plans", headers=teacher).status_code == 403
            assert {item["id"] for item in client.get("/api/v1/knowledge-bases", headers=student).json()} == {own_base}
            assert client.get(f"/api/v1/knowledge-bases/{other_base}/documents", headers=student).status_code == 404
            assert client.get(f"/api/v1/documents/{other_document}/content", headers=student).status_code == 404
            assert client.post("/api/v1/questions/ask", headers=student, json={
                "question": "什么是虚拟内存？", "knowledge_base_id": other_base, "answer_mode": "rag",
            }).status_code == 404
            own_document_names = {
                item["name"] for item in client.get(f"/api/v1/knowledge-bases/{own_base}/documents", headers=student).json()
            }
            unscoped_retrieval = client.post("/api/v1/questions/retrieve", headers=student, json={
                "question": "什么是二叉树？",
            })
            assert unscoped_retrieval.status_code == 200, unscoped_retrieval.text
            assert all(item["document_name"] in own_document_names for item in unscoped_retrieval.json()["citations"])
            questions = client.get("/api/v1/questions", headers=student).json()
            assert questions and all(item["course_id"] == course["id"] for item in questions)

            removed = client.patch(f"/api/v1/courses/{course['id']}/members/{user_id}", headers=teacher,
                                   json={"status": "removed"})
            assert removed.status_code == 200 and removed.json()["status"] == "removed"
            assert client.get("/api/v1/courses", headers=student).json() == []
            assert client.get("/api/v1/questions", headers=student).json() == []
            assert client.get("/api/v1/assignments", headers=student).json() == []
            assert client.get("/api/v1/study-plans", headers=student).json() == []

            restored = client.patch(f"/api/v1/courses/{course['id']}/members/{user_id}", headers=teacher,
                                    json={"status": "active"})
            assert restored.status_code == 200 and restored.json()["status"] == "active"
            assert len(client.get("/api/v1/courses", headers=student).json()) == 1
        finally:
            if user_id:
                with psycopg.connect(DATABASE_URL) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("DELETE FROM users WHERE id = %s AND username = %s", (user_id, username))


def test_new_teacher_knowledge_base_stays_accessible_until_course_binding() -> None:
    name = f"待关联课程资料-{uuid4().hex[:10]}"
    knowledge_base_id = None
    with httpx.Client(base_url=BASE_URL, timeout=20) as client:
        teacher = _login(client, "teacher", "teacher123")
        admin = _login(client, "admin", "admin123")
        try:
            created = client.post("/api/v1/knowledge-bases", headers=teacher, json={
                "name": name, "course": "待关联课程", "description": "验收用临时资料库",
            })
            assert created.status_code == 201, created.text
            knowledge_base_id = created.json()["id"]
            assert knowledge_base_id in {
                item["id"] for item in client.get("/api/v1/knowledge-bases", headers=teacher).json()
            }
            assert client.get(
                f"/api/v1/knowledge-bases/{knowledge_base_id}/documents", headers=teacher
            ).status_code == 200
            assert client.delete(f"/api/v1/knowledge-bases/{knowledge_base_id}", headers=admin).status_code == 409
            confirmed = client.delete(f"/api/v1/knowledge-bases/{knowledge_base_id}", headers={
                **admin, "X-Confirm-Action": "true",
            })
            assert confirmed.status_code == 204, confirmed.text
            audits = client.get("/api/v1/admin/audit-logs?limit=100", headers=admin)
            assert audits.status_code == 200, audits.text
            assert any(item["action"] == "delete" and item["resource_type"] == "knowledge_base"
                       and item["resource_id"] == knowledge_base_id
                       and item["detail"].get("confirmed") is True
                       for item in audits.json())
        finally:
            if knowledge_base_id:
                with psycopg.connect(DATABASE_URL) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("DELETE FROM knowledge_bases WHERE id = %s AND name = %s",
                                       (knowledge_base_id, name))


def test_late_submission_and_adaptive_practice_lifecycle() -> None:
    suffix = uuid4().hex[:10]
    username = f"accept_{suffix}"
    password = "Acceptance123!"
    user_id = assignment_id = late_request_id = None
    with httpx.Client(base_url=BASE_URL, timeout=20) as client:
        admin = _login(client, "admin", "admin123")
        teacher = _login(client, "teacher", "teacher123")
        try:
            created = client.post("/api/v1/admin/users", headers=admin, json={
                "username": username, "display_name": "自动验收学生", "role": "student", "password": password,
            })
            assert created.status_code == 201, created.text
            user_id = created.json()["id"]
            student = _login(client, username, password)
            joined = client.post("/api/v1/classes/join", headers=student, json={"invite_code": "DS2026"})
            assert joined.status_code == 200, joined.text

            questions = client.get("/api/v1/questions", headers=teacher).json()
            joined_class = joined.json()
            objective = next(item for item in questions if item["course_id"] == joined_class["course_id"]
                             and item["question_type"] != "short_answer")
            created_assignment = client.post("/api/v1/assignments", headers=teacher, json={
                "class_id": joined_class["id"], "title": f"自动验收作业-{suffix}",
                "description": "测试结束后自动清理", "question_ids": [objective["id"]],
                "due_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            })
            assert created_assignment.status_code == 201, created_assignment.text
            assignment_id = created_assignment.json()["id"]
            answers = {objective["id"]: objective["correct_answer"]}

            blocked = client.post(f"/api/v1/assignments/{assignment_id}/submit", headers=student, json={"answers": answers})
            assert blocked.status_code == 409
            requested = client.post(f"/api/v1/assignments/{assignment_id}/late-requests", headers=student,
                                    json={"reason": "自动验收：申请补交"})
            assert requested.status_code == 201, requested.text
            late_request_id = requested.json()["id"]
            approved = client.patch(f"/api/v1/late-submission-requests/{late_request_id}", headers=teacher, json={
                "status": "approved", "review_note": "自动验收批准",
                "approved_until": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            })
            assert approved.status_code == 200 and approved.json()["status"] == "approved"
            submitted = client.post(f"/api/v1/assignments/{assignment_id}/submit", headers=student,
                                    json={"answers": answers})
            assert submitted.status_code == 200, submitted.text
            requests = client.get(f"/api/v1/late-submission-requests?assignment_id={assignment_id}", headers=teacher).json()
            assert requests[0]["status"] == "used"

            practice = client.get("/api/v1/practice/recommendations?limit=10", headers=student).json()
            target = next(item for item in practice if item["question"]["question_type"] != "short_answer")
            teacher_question = next(item for item in questions if item["id"] == target["question"]["id"])
            endpoint = f"/api/v1/practice/questions/{target['question']['id']}/attempt"
            wrong = client.post(endpoint, headers=student, json={"answer": "__wrong__"})
            first = client.post(endpoint, headers=student, json={"answer": teacher_question["correct_answer"]})
            second = client.post(endpoint, headers=student, json={"answer": teacher_question["correct_answer"]})
            assert wrong.json()["is_correct"] is False
            assert first.json()["correct_streak"] == 1
            assert second.json()["mastered"] is True
        finally:
            with psycopg.connect(DATABASE_URL) as connection:
                with connection.cursor() as cursor:
                    if late_request_id:
                        cursor.execute("DELETE FROM audit_logs WHERE resource_id = %s", (late_request_id,))
                    if assignment_id:
                        cursor.execute("DELETE FROM assignments WHERE id = %s", (assignment_id,))
                    if user_id:
                        cursor.execute("DELETE FROM audit_logs WHERE resource_id = %s OR actor_id = %s", (user_id, user_id))
                        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))


def test_confirmed_role_change_updates_existing_session_and_audit() -> None:
    username = f"role_verify_{uuid4().hex[:10]}"
    password = "Acceptance123!"
    user_id = None
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        admin = _login(client, "admin", "admin123")
        try:
            created = client.post("/api/v1/admin/users", headers=admin, json={
                "username": username, "display_name": "角色验收临时账号",
                "role": "student", "password": password,
            })
            assert created.status_code == 201, created.text
            user_id = created.json()["id"]
            previous_session = _login(client, username, password)
            assert client.get("/api/v1/auth/me", headers=previous_session).json()["role"] == "student"

            changed = client.patch(f"/api/v1/admin/users/{user_id}/role", headers=admin, json={
                "role": "teacher", "reason": "在线验收临时账号角色调整", "confirmed": True,
            })
            assert changed.status_code == 200, changed.text
            assert changed.json()["role"] == "teacher"
            assert client.get("/api/v1/auth/me", headers=previous_session).json()["role"] == "teacher"
            audits = client.get("/api/v1/admin/audit-logs?limit=100", headers=admin)
            assert audits.status_code == 200, audits.text
            assert any(item["action"] == "change_role" and item["resource_id"] == user_id
                       and item["detail"].get("from_role") == "student"
                       and item["detail"].get("to_role") == "teacher"
                       for item in audits.json())
        finally:
            if user_id:
                with psycopg.connect(DATABASE_URL) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("DELETE FROM audit_logs WHERE resource_id = %s OR actor_id = %s",
                                       (user_id, user_id))
                        cursor.execute("DELETE FROM users WHERE id = %s AND username = %s", (user_id, username))


def test_local_assignment_review_publish_and_stale_visibility() -> None:
    """Exercise the deployed review lifecycle without calling an external model."""
    title = f"站内讲评验收-{uuid4().hex[:10]}"
    assignment_id = draft_id = None
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        teacher = _login(client, "teacher", "teacher123")
        student = _login(client, "student", "student123")
        other_student = _login(client, "student02", "student123")
        admin = _login(client, "admin", "admin123")
        try:
            teacher_courses = client.get("/api/v1/courses", headers=teacher).json()
            student_courses = {item["id"] for item in client.get("/api/v1/courses", headers=student).json()}
            other_courses = {item["id"] for item in client.get("/api/v1/courses", headers=other_student).json()}
            questions = client.get("/api/v1/questions", headers=teacher).json()
            course = next(item for item in teacher_courses if item["id"] in student_courses & other_courses
                          and any(question["course_id"] == item["id"] and question["question_type"] == "single_choice"
                                  for question in questions))
            question = next(item for item in questions if item["course_id"] == course["id"]
                            and item["question_type"] == "single_choice")
            created = client.post("/api/v1/assignments", headers=teacher, json={
                "course_id": course["id"], "title": title, "question_ids": [question["id"]], "status": "draft",
            })
            assert created.status_code == 201, created.text
            assignment_id = created.json()["id"]
            publish_assignment = client.patch(f"/api/v1/assignments/{assignment_id}/status", headers=teacher,
                                              json={"status": "published"})
            assert publish_assignment.status_code == 200, publish_assignment.text
            answers = {question["id"]: question["correct_answer"]}
            first_submission = client.post(f"/api/v1/assignments/{assignment_id}/submit", headers=student,
                                           json={"answers": answers})
            assert first_submission.status_code == 200, first_submission.text
            assert first_submission.json()["status"] == "graded"
            path = f"/api/v1/assignments/{assignment_id}/review"
            assert client.get(path, headers=student).status_code == 404

            local = client.post(f"/api/v1/assignments/{assignment_id}/review-drafts", headers=teacher,
                                json={"local_only": True})
            assert local.status_code == 201, local.text
            draft_id = local.json()["id"]
            assert local.json()["source_context"]["model"] == "local-statistics"
            assert "当前未使用在线模型" in local.json()["content"]
            edited = client.patch(f"/api/v1/teaching-drafts/{draft_id}", headers=teacher, json={
                "content": local.json()["content"] + "\n\n### 教师补充\n请复习本题相关概念。",
                "status": "confirmed",
            })
            assert edited.status_code == 200 and edited.json()["status"] == "confirmed", edited.text
            published = client.post(f"/api/v1/teaching-drafts/{draft_id}/publish-review", headers=teacher)
            assert published.status_code == 200 and published.json()["status"] == "published", published.text
            visible = client.get(path, headers=student)
            assert visible.status_code == 200 and "教师补充" in visible.json()["content"]
            assert client.get(path, headers=other_student).status_code == 404
            audits = client.get("/api/v1/admin/audit-logs?limit=100", headers=admin)
            assert audits.status_code == 200
            assert any(item["action"] == "publish_assignment_review" and item["resource_id"] == assignment_id
                       and item["detail"].get("draft_id") == draft_id for item in audits.json())

            second_submission = client.post(f"/api/v1/assignments/{assignment_id}/submit", headers=other_student,
                                            json={"answers": answers})
            assert second_submission.status_code == 200, second_submission.text
            assert client.get(path, headers=student).status_code == 404
            stale = client.get(path, headers=teacher)
            assert stale.status_code == 200 and stale.json()["stale"] is True
        finally:
            if assignment_id or draft_id:
                with psycopg.connect(DATABASE_URL) as connection:
                    with connection.cursor() as cursor:
                        if assignment_id:
                            cursor.execute("DELETE FROM assignments WHERE id = %s AND title = %s",
                                           (assignment_id, title))
                        if draft_id:
                            cursor.execute("DELETE FROM teaching_drafts WHERE id = %s AND title = %s",
                                           (draft_id, f"{title} · 作业讲评"))
                        cursor.execute("DELETE FROM audit_logs WHERE resource_id = %s OR resource_id = %s",
                                       (assignment_id, draft_id))
                        cursor.execute("SELECT count(*) FROM assignments WHERE id = %s AND title = %s",
                                       (assignment_id, title))
                        assert cursor.fetchone()[0] == 0
                        cursor.execute("SELECT count(*) FROM teaching_drafts WHERE id = %s", (draft_id,))
                        assert cursor.fetchone()[0] == 0
                        cursor.execute("SELECT count(*) FROM audit_logs WHERE resource_id = %s OR resource_id = %s",
                                       (assignment_id, draft_id))
                        assert cursor.fetchone()[0] == 0
