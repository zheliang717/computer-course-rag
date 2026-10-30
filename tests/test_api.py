from fastapi.testclient import TestClient
from pathlib import Path
from uuid import uuid4

from app import main as main_module
from app.auth import Principal
from app.main import app
from app.rag import RetrievalResult


client = TestClient(app)


def test_login_and_system_status_flow() -> None:
    login = client.post("/api/v1/auth/login", json={"username": "student", "password": "student123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "student"
    status = client.get("/api/v1/system", headers={"Authorization": f"Bearer {token}"})
    assert status.status_code == 200
    assert status.json()["llm_provider"] == "offline"


def test_student_cannot_create_course() -> None:
    login = client.post("/api/v1/auth/login", json={"username": "student", "password": "student123"})
    token = login.json()["access_token"]
    response = client.post(
        "/api/v1/courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "操作系统", "code": "OS-2026", "status": "draft"},
    )
    assert response.status_code == 403


def test_platform_routes_are_registered() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/dashboard" in paths
    assert "/api/v1/courses" in paths
    assert "/api/v1/courses/{course_id}/sections" in paths
    assert "/api/v1/courses/{course_id}" in paths
    assert "/api/v1/courses/{course_id}/classes" in paths
    assert "/api/v1/classes/join" in paths
    assert "/api/v1/classes/{class_id}/members" in paths
    assert "/api/v1/classes/{class_id}/members/{member_id}" in paths
    assert "/api/v1/classes/{class_id}/announcements" in paths
    assert "/api/v1/questions" in paths
    assert "/api/v1/teaching-drafts" in paths
    assert "/api/v1/teaching-drafts/{draft_id}" in paths
    assert "/api/v1/assignments" in paths
    assert "/api/v1/assignments/{assignment_id}/submit" in paths
    assert "/api/v1/assignments/{assignment_id}/late-requests" in paths
    assert "/api/v1/late-submission-requests" in paths
    assert "/api/v1/late-submission-requests/{request_id}" in paths
    assert "/api/v1/wrong-questions" in paths
    assert "/api/v1/practice/recommendations" in paths
    assert "/api/v1/practice/questions/{question_id}/attempt" in paths
    assert "/api/v1/courses/{course_id}/knowledge-bases" in paths
    assert "/api/v1/courses/{course_id}/knowledge-points" in paths
    assert "/api/v1/learning/progress" in paths
    assert "/api/v1/learning/reports" in paths
    assert "/api/v1/study-plans" in paths
    assert "/api/v1/study-notes" in paths
    assert "/api/v1/study-notes/{note_id}" in paths
    assert "/api/v1/classes/{class_id}/analytics" in paths
    assert "/api/v1/admin/metrics" in paths
    assert "/api/v1/admin/users" in paths
    assert "/api/v1/admin/model-config" in paths
    assert "/api/v1/admin/audit-logs" in paths
    assert "/api/v1/assignments/{assignment_id}/status" in paths
    assert "/api/v1/assignments/{assignment_id}/submissions" in paths
    assert "/api/v1/submissions/{submission_id}/grade" in paths
    assert "/api/v1/question-reviews" in paths
    assert "/api/v1/question-reviews/{history_id}" in paths
    assert "/api/v1/knowledge-bases/{knowledge_base_id}/document-jobs" in paths
    assert "/api/v1/knowledge-bases/{knowledge_base_id}/text-documents" in paths
    assert "/api/v1/document-jobs" in paths
    assert "/api/v1/document-jobs/{job_id}" in paths
    assert "/api/v1/document-jobs/{job_id}/retry" in paths
    assert "/api/v1/documents/{document_id}" in paths
    assert "/api/v1/documents/{document_id}/content" in paths
    assert "/api/v1/tutor/conversations" in paths
    assert "/api/v1/tutor/conversations/{conversation_id}/messages" in paths
    assert "/api/v1/history/{history_id}/favorite" in paths
    assert "/api/v1/history/{history_id}/export" in paths
    assert "/api/v1/admin/security" in paths
    assert "/api/v1/admin/evaluations" in paths
    assert "/api/v1/admin/evaluations/{run_id}" in paths


def test_student_cannot_access_admin_metrics() -> None:
    login = client.post("/api/v1/auth/login", json={"username": "student", "password": "student123"})
    token = login.json()["access_token"]
    response = client.get("/api/v1/admin/metrics", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_health_and_text_retrieval_flow() -> None:
    imported = client.post(
        "/api/v1/knowledge/texts",
        json={
            "pages": [
                {
                    "document_id": "course-1",
                    "document_name": "数据结构.pdf",
                    "page_number": 6,
                    "chapter": "线性表",
                    "text": "栈是一种后进先出的线性表，只允许在栈顶插入和删除元素。",
                }
            ]
        },
    )
    assert imported.status_code == 200
    assert imported.json()["imported_chunks"] == 1

    response = client.post("/api/v1/questions/retrieve", json={"question": "栈是不是后进先出？"})
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["citations"][0]["page_number"] == 6
    assert body["citations"][0]["document_name"] == "数据结构.pdf"


def test_pdf_endpoint_rejects_non_pdf() -> None:
    response = client.post(
        "/api/v1/knowledge/pdf",
        data={"document_id": "bad"},
        files={"file": ("bad.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 415


def test_pdf_endpoint_imports_valid_pdf_bytes() -> None:
    path = Path("materials/test-data/computer-course-rag-test-data.pdf")
    with path.open("rb") as stream:
        response = client.post(
            "/api/v1/knowledge/pdf",
            data={"document_id": "test-pdf"},
            files={"file": (path.name, stream, "application/pdf")},
        )
    assert response.status_code == 200
    assert response.json()["imported_chunks"] > 0


def test_ask_history_and_feedback_flow() -> None:
    imported = client.post(
        "/api/v1/knowledge/texts",
        json={
            "pages": [
                {
                    "document_id": "history-course-1",
                    "document_name": "算法基础",
                    "page_number": 2,
                    "chapter": "递归",
                    "text": "递归算法通过调用自身解决规模更小的同类问题。",
                }
            ]
        },
    )
    assert imported.status_code == 200

    answer = client.post("/api/v1/questions/ask", json={"question": "递归算法如何工作？"})
    assert answer.status_code == 200
    history_id = answer.json()["history_id"]
    assert history_id

    history = client.get("/api/v1/history?limit=5")
    assert history.status_code == 200
    assert any(item["id"] == history_id for item in history.json())

    feedback = client.post(f"/api/v1/history/{history_id}/feedback", json={"rating": 5})
    assert feedback.status_code == 200
    assert feedback.json()["rating"] == 5


def test_answer_modes_switch_generation_strategy(monkeypatch) -> None:
    class EmptyRetrieval:
        def retrieve(self, question: str, knowledge_base_id: str | None = None) -> RetrievalResult:
            del question, knowledge_base_id
            return RetrievalResult(accepted=False, message="没有课程证据。", hits=[])

    class FakeGenerator:
        def generate(self, question: str, hits, *, grounded: bool = True) -> str:
            del question, hits
            return "课程回答" if grounded else "通用回答"

    monkeypatch.setattr(main_module, "retrieval", EmptyRetrieval())
    monkeypatch.setattr(main_module, "generator", FakeGenerator())

    rag = client.post("/api/v1/questions/ask", json={"question": "天气怎么样？", "answer_mode": "rag"})
    assert rag.status_code == 200
    assert rag.json()["accepted"] is False
    assert rag.json()["answer_mode"] == "rag"

    general = client.post("/api/v1/questions/ask", json={"question": "天气怎么样？", "answer_mode": "general"})
    assert general.status_code == 200
    assert general.json()["accepted"] is True
    assert general.json()["answer_mode"] == "general"
    assert general.json()["answer"] == "通用回答"
    assert general.json()["citations"] == []

    hybrid = client.post("/api/v1/questions/ask", json={"question": "天气怎么样？", "answer_mode": "hybrid"})
    assert hybrid.status_code == 200
    assert hybrid.json()["accepted"] is True
    assert hybrid.json()["answer_mode"] == "hybrid"
    assert hybrid.json()["answer"] == "通用回答"


def test_embedded_assistant_uses_concise_generation_task(monkeypatch) -> None:
    tasks: list[str] = []

    class FakeGenerator:
        def generate(self, question: str, hits, *, grounded: bool = True, task: str = "answer") -> str:
            del question, hits, grounded
            tasks.append(task)
            return "简明讲解"

    monkeypatch.setattr(main_module, "generator", FakeGenerator())
    response = client.post("/api/v1/questions/ask", json={
        "question": "进程和线程有什么区别？", "answer_mode": "general", "assistant_scope": "course_qa",
    })
    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "简明讲解"
    assert tasks == ["assistant_chat"]


def test_assistant_history_can_be_resumed_only_by_its_owner(monkeypatch) -> None:
    class FakeGenerator:
        def generate(self, question: str, hits, *, grounded: bool = True, task: str = "answer") -> str:
            del question, hits, grounded, task
            return "进程有独立资源，线程共享所属进程的资源。"

    monkeypatch.setattr(main_module, "generator", FakeGenerator())
    owner = Principal(id=str(uuid4()), username="owner", display_name="Owner", role="student")
    outsider = Principal(id=str(uuid4()), username="outsider", display_name="Outsider", role="teacher")

    class TestAuth:
        required = True

        def verify_token(self, token: str):
            return {"owner": owner, "outsider": outsider}.get(token)

    monkeypatch.setattr(main_module, "auth", TestAuth())
    student_headers = {"Authorization": "Bearer owner"}
    teacher_headers = {"Authorization": "Bearer outsider"}
    answer = client.post("/api/v1/questions/ask", headers=student_headers, json={
        "question": "进程和线程有什么区别？", "answer_mode": "general", "assistant_scope": "course_qa",
    })
    assert answer.status_code == 200, answer.text
    conversation_id = answer.json()["conversation_id"]
    student_list = client.get("/api/v1/tutor/conversations", headers=student_headers)
    assert student_list.status_code == 200
    assert any(item["id"] == conversation_id for item in student_list.json())
    restored = client.get(f"/api/v1/tutor/conversations/{conversation_id}/messages", headers=student_headers)
    assert restored.status_code == 200
    assert restored.json()[-1]["answer"] == "进程有独立资源，线程共享所属进程的资源。"
    outsider = client.get(f"/api/v1/tutor/conversations/{conversation_id}/messages", headers=teacher_headers)
    assert outsider.status_code == 200
    assert outsider.json() == []


def test_student_schedule_answer_uses_platform_context_without_textbook_retrieval(monkeypatch) -> None:
    prompts: list[str] = []

    class UnexpectedRetrieval:
        def retrieve(self, question: str, knowledge_base_id: str | None = None) -> RetrievalResult:
            raise AssertionError("General platform-data questions must not search textbook chunks")

    class CapturingGenerator:
        def generate(self, question: str, hits, *, grounded: bool = True) -> str:
            assert not hits and not grounded
            prompts.append(question)
            return "根据课表，今天有一节数据结构课。"

    monkeypatch.setattr(main_module, "retrieval", UnexpectedRetrieval())
    monkeypatch.setattr(main_module, "generator", CapturingGenerator())
    token = client.post("/api/v1/auth/login", json={"username": "student", "password": "student123"}).json()["access_token"]
    response = client.post("/api/v1/questions/ask", headers={"Authorization": f"Bearer {token}"}, json={
        "question": "我今天有什么课？", "answer_mode": "general",
        "page_context": "今日课次：数据结构 第三次课 9月29日 10:00 教学楼101",
    })
    assert response.status_code == 200, response.text
    assert response.json()["citations"] == []
    assert "今日课次：数据结构" in prompts[0]
    assert "不要编造" in prompts[0]


def test_tutor_conversation_quick_action_uses_previous_context(monkeypatch) -> None:
    prompts: list[str] = []

    class EmptyRetrieval:
        def retrieve(self, question: str, knowledge_base_id: str | None = None) -> RetrievalResult:
            del question, knowledge_base_id
            return RetrievalResult(accepted=False, message="没有课程证据。", hits=[])

    class CapturingGenerator:
        def generate(self, question: str, hits, *, grounded: bool = True) -> str:
            del hits, grounded
            prompts.append(question)
            return "教学回答"

    monkeypatch.setattr(main_module, "retrieval", EmptyRetrieval())
    monkeypatch.setattr(main_module, "generator", CapturingGenerator())
    first = client.post("/api/v1/questions/ask", json={"question": "什么是二叉树？", "answer_mode": "general"})
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]
    second = client.post("/api/v1/questions/ask", json={
        "question": "请继续", "answer_mode": "general", "conversation_id": conversation_id,
        "quick_action": "example",
    })
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id
    assert "什么是二叉树" in prompts[-1]
    assert "具体、完整" in prompts[-1]


def test_practice_quick_action_never_exposes_model_answer(monkeypatch) -> None:
    class FakeGenerator:
        def generate(self, question: str, hits, *, grounded: bool = True, task: str = "answer") -> str:
            del question, hits, grounded
            return ('{"question":"请比较栈和队列。","answer":"栈后进先出"}'
                    if task == "practice_question" else "先复习栈和队列。")

    monkeypatch.setattr(main_module, "generator", FakeGenerator())
    first = client.post("/api/v1/questions/ask", json={"question": "栈和队列", "answer_mode": "general"})
    assert first.status_code == 200
    response = client.post("/api/v1/questions/ask", json={
        "question": "生成练习", "answer_mode": "general",
        "conversation_id": first.json()["conversation_id"], "quick_action": "practice",
    })
    assert response.status_code == 200
    assert "请比较栈和队列" in response.json()["answer"]
    assert "栈后进先出" not in response.json()["answer"]
    assert response.json()["citations"] == []
