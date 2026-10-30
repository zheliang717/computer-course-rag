"""Read-only live API and role-permission checks.

Run with LIVE_API_TESTS=1 after `docker compose up -d`.
"""
import os
import time
from uuid import uuid4

import httpx
import pytest


pytestmark = pytest.mark.skipif(os.getenv("LIVE_API_TESTS") != "1", reason="requires the live Docker stack")
BASE_URL = os.getenv("LIVE_API_URL", "http://127.0.0.1:8000")
if os.getenv('LIVE_API_TESTS') == '1' and BASE_URL != 'http://127.0.0.1:18084':
    raise RuntimeError('Use the isolated API copy on 18084 for acceptance tests')
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


def test_three_role_live_acceptance() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=15) as client:
        student = _login(client, "student", "student123")
        teacher = _login(client, "teacher", "teacher123")
        admin = _login(client, "admin", "admin123")

        for headers, expected_role in ((student, "student"), (teacher, "teacher"), (admin, "admin")):
            response = client.get("/api/v1/auth/me", headers=headers)
            assert response.status_code == 200
            assert response.json()["role"] == expected_role
            assert response.headers.get("x-request-id")

        assert client.get("/api/v1/dashboard", headers=student).status_code == 200
        assert client.get("/api/v1/practice/recommendations", headers=student).status_code == 200
        assert client.get("/api/v1/question-reviews", headers=teacher).status_code == 200
        assert client.get("/api/v1/late-submission-requests", headers=teacher).status_code == 200
        model_config = client.get("/api/v1/admin/model-config", headers=admin)
        assert model_config.status_code == 200
        assert "api_key" not in model_config.json()

        assert client.get("/api/v1/admin/metrics", headers=student).status_code == 403
        assert client.get("/api/v1/admin/metrics", headers=teacher).status_code == 403
        assert client.get("/api/v1/practice/recommendations", headers=admin).status_code == 403
        assert client.patch(
            f"/api/v1/late-submission-requests/{uuid4()}",
            headers=student,
            json={"status": "approved"},
        ).status_code == 403

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"


def test_all_paged_lists_live() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=15) as client:
        admin = _login(client, "admin", "admin123")
        teacher = _login(client, "teacher", "teacher123")
        student = _login(client, "student", "student123")
        for resource in ("users", "audits", "evaluations", "logins", "requests", "model-calls", "courses",
                         "jobs", "drafts", "reviews", "assignments", "late-requests", "history"):
            response = client.get(f"/api/v1/paged/{resource}?page_size=2", headers=admin)
            assert response.status_code == 200, f"{resource}: {response.text}"
            data = response.json()
            assert data["page"] == 1 and data["page_size"] == 2
            assert len(data["items"]) <= 2 and data["total"] >= len(data["items"])
        for resource in ("wrong-questions", "notes", "history", "assignments", "courses"):
            response = client.get(f"/api/v1/paged/{resource}?page_size=2", headers=student)
            assert response.status_code == 200, f"{resource}: {response.text}"
        for headers in (teacher, student):
            assert client.get("/api/v1/paged/users", headers=headers).status_code == 403
            assert client.get("/api/v1/paged/requests", headers=headers).status_code == 403
        courses = client.get("/api/v1/courses", headers=teacher).json()
        assert courses
        course_id = courses[0]["id"]
        for resource in ("members", "sessions"):
            response = client.get(f"/api/v1/paged/{resource}?scope_id={course_id}&page_size=2", headers=teacher)
            assert response.status_code == 200, response.text
        bases = client.get(f"/api/v1/courses/{course_id}/knowledge-bases", headers=teacher).json()
        if bases:
            assert client.get(f"/api/v1/paged/documents?scope_id={bases[0]['id']}&page_size=2", headers=teacher).status_code == 200
        tasks = client.get("/api/v1/assignments", headers=teacher).json()
        if tasks:
            assert client.get(f"/api/v1/paged/submissions?scope_id={tasks[0]['id']}&page_size=2", headers=teacher).status_code == 200
def test_open_textbooks_are_bound_to_the_right_courses() -> None:
    expected = {
        "OS-2026": ("Think OS: A Brief Introduction to Operating Systems", "什么是虚拟内存？"),
        "NET-2026": ("Computer Networks: A Systems Approach", "TCP流量控制如何工作？"),
    }
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        student = _login(client, "student", "student123")
        teacher = _login(client, "teacher", "teacher123")
        courses = {item["code"]: item for item in client.get("/api/v1/courses", headers=student).json()}
        for code, (title, question) in expected.items():
            course = courses[code]
            response = client.get(f"/api/v1/courses/{course['id']}/knowledge-bases", headers=student)
            assert response.status_code == 200, response.text
            bases = response.json()
            assert len(bases) == 1
            documents = client.get(f"/api/v1/knowledge-bases/{bases[0]['id']}/documents", headers=student)
            assert documents.status_code == 200, documents.text
            assert documents.json()
            document = next(item for item in documents.json() if item["name"] == title)
            assert document["source_url"].startswith("https://")
            assert document["license_name"].startswith("Creative Commons")
            assert document["status"] == "ready"
            result = client.post("/api/v1/questions/retrieve", headers=student, json={
                "question": question, "knowledge_base_id": bases[0]["id"],
            })
            assert result.status_code == 200, result.text
            assert result.json()["accepted"]
            citation = next(item for item in result.json()["citations"] if item["document_name"] == title)
            assert citation["document_id"] == document["id"]
            assert citation["chunk_id"]
            original = client.get(f"/api/v1/documents/{citation['document_id']}/content", headers=student)
            assert original.status_code == 200, original.text
            assert any(page["page_number"] == citation["page_number"] for page in original.json()["pages"])


def test_student_note_round_trip_uses_published_course_page() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        student = _login(client, "student", "student123")
        teacher = _login(client, "teacher", "teacher123")
        course = next(item for item in client.get("/api/v1/courses", headers=student).json() if item["code"] == "DSA-2026")
        base = client.get(f"/api/v1/courses/{course['id']}/knowledge-bases", headers=student).json()[0]
        document = client.get(f"/api/v1/knowledge-bases/{base['id']}/documents", headers=student).json()[0]
        content = client.get(f"/api/v1/documents/{document['id']}/content", headers=student).json()
        page = next(item for item in content["pages"] if len(item["content"].strip()) >= 20)
        excerpt = page["content"].strip()[:100]
        payload = {"course_id": course["id"], "document_id": document["id"], "page_number": page["page_number"],
                   "excerpt": excerpt, "content": "在线测试临时摘录", "origin": "excerpt"}
        assert client.post("/api/v1/study-notes", headers=teacher, json=payload).status_code == 403
        created = client.post("/api/v1/study-notes", headers=student, json=payload)
        assert created.status_code == 201, created.text
        note_id = created.json()["id"]
        try:
            assert any(item["id"] == note_id for item in client.get("/api/v1/study-notes", headers=student).json())
        finally:
            assert client.delete(f"/api/v1/study-notes/{note_id}", headers=student).status_code == 204


def test_course_announcements_preserve_history_and_enforce_roles() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        student = _login(client, "student", "student123")
        teacher = _login(client, "teacher", "teacher123")
        courses = {item["code"]: item for item in client.get("/api/v1/courses", headers=student).json()}
        for code in ("DSA-2026", "OS-2026", "NET-2026"):
            course_id = courses[code]["id"]
            response = client.get(f"/api/v1/courses/{course_id}/announcements", headers=student)
            assert response.status_code == 200, response.text
            notices = response.json()
            assert notices, f"{code} should retain a migrated course announcement"
            assert all(item["course_id"] == course_id for item in notices)
            assert all(item["title"] and item["content"] for item in notices)
            assert client.get(f"/api/v1/courses/{course_id}/announcements", headers=teacher).status_code == 200
            assert client.post(
                f"/api/v1/courses/{course_id}/announcements",
                headers=student,
                json={"title": "学生不应发布", "content": "权限测试"},
            ).status_code == 403


def test_admin_operations_report_live() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        admin = _login(client, "admin", "admin123")
        student = _login(client, "student", "student123")
        for days in (1, 7, 30):
            response = client.get(f"/api/v1/admin/operations-report?days={days}", headers=admin)
            assert response.status_code == 200, response.text
            report = response.json()
            assert report["period_days"] == days
            assert report["overall_status"] in {"healthy", "warning"}
            assert report["metrics"]["published_courses"] >= 1
            assert {item["id"] for item in report["checks"]} == {
                "course_materials", "document_jobs", "model_calls", "security", "accounts",
            }
        assert client.get("/api/v1/admin/operations-report?days=1", headers=student).status_code == 403


def test_assignment_review_requires_teacher_and_explicit_online_consent() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        student = _login(client, "student", "student123")
        teacher = _login(client, "teacher", "teacher123")
        system = client.get("/api/v1/system", headers=teacher)
        assert system.status_code == 200
        if system.json()["llm_provider"] == "offline":
            pytest.skip("the live model is offline; the no-consent branch would create an offline draft")
        assignments = client.get("/api/v1/assignments", headers=teacher)
        assert assignments.status_code == 200
        assignment_id = next((item["id"] for item in assignments.json()
                              if client.get(f"/api/v1/assignments/{item['id']}/submissions", headers=teacher).json()), None)
        if assignment_id is None:
            pytest.skip("no submitted demo assignment available")
        path = f"/api/v1/assignments/{assignment_id}/review-drafts"
        assert client.post(path, headers=student, json={}).status_code == 403
        refused = client.post(path, headers=teacher, json={"confirm_external_analysis": False})
        assert refused.status_code == 409
        # The current API requires an explicit AI-review action, rather than
        # relying on the older consent-only error wording.
        assert "明确" in refused.json()['detail'] and "讲评" in refused.json()['detail']


def test_student_agenda_answer_uses_platform_records_without_model() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        student = _login(client, "student", "student123")
        teacher = _login(client, "teacher", "teacher123")
        course_ids = {item["id"] for item in client.get("/api/v1/courses", headers=student).json()}
        for question in ("今天有什么课？", "下一个作业是什么？"):
            response = client.post("/api/v1/questions/ask", headers=student, json={
                "question": question, "answer_mode": "general", "assistant_scope": "course_qa",
                "page_context": "伪造：秘密课程今天在 Z999 上课。",
            })
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["model"] == "platform-data" and not data["citations"]
            assert "秘密课程" not in data["answer"] and "Z999" not in data["answer"]
            assert all(action["kind"] in {"course", "assignment"} for action in data["actions"])
            assert all(action["target_id"] in course_ids for action in data["actions"] if action["kind"] == "course")
            conversation_path = f"/api/v1/tutor/conversations/{data['conversation_id']}/messages"
            restored = client.get(conversation_path, headers=student)
            assert restored.status_code == 200 and restored.json()[-1]["actions"] == data["actions"]
            assert client.get(conversation_path, headers=teacher).json() == []
        denied = client.post("/api/v1/questions/ask", headers=student, json={
            "question": "今天有什么课？", "answer_mode": "general", "assistant_scope": "course_qa",
            "assistant_course_id": str(uuid4()),
        })
        assert denied.status_code == 404


def test_role_change_is_admin_only_and_refuses_unconfirmed_live() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        admin = _login(client, "admin", "admin123")
        student = _login(client, "student", "student123")
        target = next(item for item in client.get("/api/v1/admin/users", headers=admin).json()
                      if item["username"] == "student02")
        path = f"/api/v1/admin/users/{target['id']}/role"
        payload = {"role": "teacher", "reason": "在线权限回归，不应真正修改"}
        assert client.patch(path, headers=student, json={**payload, "confirmed": True}).status_code == 403
        refused = client.patch(path, headers=admin, json=payload)
        assert refused.status_code == 409 and "二次确认" in refused.text
        after = next(item for item in client.get("/api/v1/admin/users", headers=admin).json()
                     if item["id"] == target["id"])
        assert after["role"] == target["role"]
        new_admin_name = f"unconfirmed_{uuid4().hex[:10]}"
        create = client.post("/api/v1/admin/users", headers=admin, json={
            "username": new_admin_name, "display_name": "未确认管理员", "role": "admin",
            "password": "Acceptance123!",
        })
        assert create.status_code == 409 and "二次确认" in create.text
        assert all(item["username"] != new_admin_name for item in
                   client.get("/api/v1/admin/users", headers=admin).json())
