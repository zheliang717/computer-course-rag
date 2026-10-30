"""AI semantic checks are opt-in, course-scoped, advisory, and never publish."""

import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.ai_question_review import parse_ai_question_review
from app.auth import Principal
from app.database import Base
from app.domain import SearchHit, TextChunk
from app.models import Course, TeachingDraft, User
from app.teaching_drafts import TeachingDraftService


def _response() -> str:
    return json.dumps({"summary": "仅发现一个需教师核对的疑点。", "findings": [
        {"category": "ambiguity", "detail": "题干没有指定遍历顺序。", "suggestion": "补充先序遍历限定。"}
    ], "suggested_stem": "先序遍历首先访问哪个结点？"}, ensure_ascii=False)


def test_review_parser_rejects_unstructured_or_oversized_output() -> None:
    assert parse_ai_question_review(f"```json\n{_response()}\n```")["findings"][0]["category"] == "ambiguity"
    with pytest.raises(ValueError):
        parse_ai_question_review("普通段落")
    with pytest.raises(ValueError):
        parse_ai_question_review(json.dumps({"summary": "ok", "findings": [{"category": "made_up"}]}))


class _Auth:
    required = True

    def __init__(self, principals):
        self.principals = principals

    def verify_token(self, token):
        return self.principals.get(token)


class _Generator:
    def __init__(self):
        self.calls = []
        self.output = _response()
        self.failure = None

    def generate(self, prompt, hits, *, grounded, task):
        self.calls.append((prompt, hits, grounded, task))
        if self.failure is not None:
            raise self.failure
        return self.output


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


class _Admin:
    def __init__(self):
        self.audits = []

    def add_audit(self, **kwargs):
        self.audits.append(kwargs)


def test_ai_review_requires_consent_and_is_advisory_with_real_evidence(monkeypatch, postgres_sessions) -> None:
    from sqlalchemy import select, func
    from app.models import KnowledgeBase, CourseKnowledgeBase, Document, Chunk, ModelQuota, ModelUsageLog
    from app.catalog import KnowledgeCatalog
    from app.assistant_context import AssistantContextService
    from app.question_reviews import QuestionReviewService
    from app.rag import RetrievalResult
    sessions = postgres_sessions
    owner_id, other_id, student_id, course_id, draft_id, base_id, document_id, chunk_id = (uuid4() for _ in range(8))
    question = {"question_type":"single_choice","stem":"首先访问哪个结点？","options":["A. 根","B. 左"],
        "correct_answer":"A","explanation":"先序先访问根。","difficulty":2,"knowledge_point":"二叉树遍历"}
    with sessions.begin() as s:
        s.add_all([User(id=identifier,username=name,display_name=name,role=role,password_hash="x") for identifier,name,role in
            [(owner_id,"review_owner","teacher"),(other_id,"review_other","teacher"),(student_id,"review_student","student")]])
        s.flush()
        s.add(Course(id=course_id,title="数据结构",code="DSA-AI-QA",owner_id=owner_id,status="published"))
        s.add(KnowledgeBase(id=base_id,name="数据结构",course="数据结构",created_by=owner_id)); s.flush()
        s.add(CourseKnowledgeBase(course_id=course_id,knowledge_base_id=base_id))
        s.add(Document(id=document_id,knowledge_base_id=base_id,filename="数据结构讲义",status="ready",publication_status="published",external_model_allowed=False))
        s.add(TeachingDraft(id=draft_id,course_id=course_id,creator_id=owner_id,draft_type="question_set",title="树题目",content="待复核题目",questions=[question],source_context={},status="draft"))
        s.add(ModelQuota(role="teacher",daily_limit=10)); s.flush()
        s.add(Chunk(id=chunk_id,document_id=document_id,page_number=3,position=0,content="先序遍历先访问根结点。",content_metadata={}))
    hit = SearchHit(TextChunk(str(chunk_id),str(document_id),"数据结构讲义",3,"先序遍历先访问根结点。"),.9)
    generator = _Generator()
    generator.output = json.dumps({"summary":"建议补全题干条件，仍需教师核对。","findings":[
        {"category":"ambiguity","detail":"题干没有指定遍历顺序。","suggestion":"补充先序遍历限定。",
         "assessment":"improvement","claim_type":"teaching_improvement",
         "anchors":[{"kind":"question","field":"stem","quote":"首先访问哪个结点？"}]}],
        "suggested_stem":"先序遍历首先访问哪个结点？","suggestion_basis":{"suggested_stem":[1]}},ensure_ascii=False)
    monkeypatch.setattr(main_module,"settings",main_module.settings.model_copy(update={"llm_provider":"compatible","llm_model":"mock-review"}))
    monkeypatch.setattr(main_module,"teaching_drafts",TeachingDraftService(sessions))
    monkeypatch.setattr(main_module,"catalog",KnowledgeCatalog(sessions))
    monkeypatch.setattr(main_module,"assistant_context",AssistantContextService(sessions))
    monkeypatch.setattr(main_module,"question_reviews",QuestionReviewService(sessions))
    monkeypatch.setattr(main_module,"generator",generator)
    monkeypatch.setattr(main_module,"auth",_Auth({
        "owner":Principal(str(owner_id),"review_owner","Owner","teacher"),
        "other":Principal(str(other_id),"review_other","Other","teacher"),
        "student":Principal(str(student_id),"review_student","Student","student")}))
    hits = [hit]
    monkeypatch.setattr(main_module,"_retrieve_for_user",lambda *args,**kwargs:RetrievalResult(True,"找到资料",hits))
    client=TestClient(main_module.app);path=f"/api/v1/teaching-drafts/{draft_id}/ai-review"
    payload={"question_index":1,"confirm_external_review":True}
    assert client.post(path,headers={"Authorization":"Bearer student"},json=payload).status_code==403
    assert client.post(path,headers={"Authorization":"Bearer other"},json=payload).status_code==404
    assert client.post(path,headers={"Authorization":"Bearer owner"},json={"question_index":1}).status_code==409
    assert client.post(path,headers={"Authorization":"Bearer owner"},json=payload).status_code==409
    assert generator.calls==[]
    with sessions.begin() as s:s.get(Document,document_id).external_model_allowed=True
    accepted=client.post(path,headers={"Authorization":"Bearer owner"},json=payload)
    assert accepted.status_code==200,accepted.text
    assert accepted.json()["grounded"] and accepted.json()["findings"][0]["category"]=="ambiguity"
    assert accepted.json()["evidence"][0]["document_name"]=="数据结构讲义"
    hits[:]=[SearchHit(TextChunk(str(uuid4()),str(uuid4()),"未核准",1,"不能发送"),1),hit]
    mixed=client.post(path,headers={"Authorization":"Bearer owner"},json=payload)
    assert mixed.status_code==200,mixed.text
    assert generator.calls[-1][1]==[hit]
    generator.output="not JSON"
    assert client.post(path,headers={"Authorization":"Bearer owner"},json=payload).status_code==409
    generator.failure=httpx.ReadTimeout("model timed out")
    timed_out=client.post(path,headers={"Authorization":"Bearer owner"},json=payload)
    assert timed_out.status_code==409 and "超时" in timed_out.json()["detail"]
    with sessions() as s:
        assert s.get(TeachingDraft,draft_id).questions==[question] and s.get(TeachingDraft,draft_id).status=="draft"
        logs=list(s.scalars(select(ModelUsageLog)))
        assert len(logs)==4 and sum(row.successful for row in logs)==2 and all(row.error_type!="pending" for row in logs)
    with sessions.begin() as s:s.get(ModelQuota,"teacher").daily_limit=0
    before=len(generator.calls)
    assert client.post(path,headers={"Authorization":"Bearer owner"},json=payload).status_code==429
    assert len(generator.calls)==before


def test_teaching_draft_uses_lower_ranked_approved_source(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    teacher_id, course_id = uuid4(), uuid4()
    with sessions.begin() as session:
        session.add(User(id=teacher_id, username="draft_teacher", display_name="Teacher",
                         role="teacher", password_hash="x"))
        session.add(Course(id=course_id, title="数据结构", code="DSA-AI-DRAFT", owner_id=teacher_id))
    allowed = SearchHit(TextChunk(chunk_id="allowed-low", document_id=str(uuid4()),
                                document_name="已核准讲义", page_number=1,
                                text="二叉树有根结点。"), score=0.7)
    blocked = [SearchHit(TextChunk(chunk_id=f"blocked-{index}", document_id=str(uuid4()),
                                   document_name="未核准讲义", page_number=1,
                                   text="不得外发的片段"), score=1.0 - index * 0.01) for index in range(6)]
    generator, admin = _Generator(), _Admin()
    generator.output = "# 二叉树教学计划\n\n先讲根结点，再安排课堂练习。"
    monkeypatch.setattr(main_module, "settings", main_module.settings.model_copy(update={
        "llm_provider": "compatible", "llm_model": "mock-draft",
    }))
    monkeypatch.setattr(main_module, "teaching_drafts", TeachingDraftService(sessions))
    monkeypatch.setattr(main_module, "auth", _Auth({
        "teacher": Principal(id=str(teacher_id), username="draft_teacher", display_name="Teacher", role="teacher"),
    }))
    monkeypatch.setattr(main_module, "learning", SimpleNamespace(get_course=lambda *args, **kwargs:
        SimpleNamespace(course=SimpleNamespace(title="数据结构"))))
    monkeypatch.setattr(main_module, "analytics", SimpleNamespace(list_course_knowledge_bases=lambda *args: [{"id": "base"}]))
    monkeypatch.setattr(main_module, "retrieval", SimpleNamespace(retrieve=lambda *args:
        SimpleNamespace(hits=blocked + [allowed])))
    monkeypatch.setattr(main_module, "catalog", SimpleNamespace(
        externally_approved_document_ids=lambda ids: ids & {UUID(allowed.chunk.document_id)}))
    monkeypatch.setattr(main_module, "generator", generator)
    monkeypatch.setattr(main_module, "model_usage", None)
    monkeypatch.setattr(main_module, "admin_service", admin)

    response = TestClient(main_module.app).post(
        "/api/v1/teaching-drafts/generate", headers={"Authorization": "Bearer teacher"},
        json={"course_id": str(course_id), "draft_type": "teaching_plan", "topic": "二叉树",
              "share_course_materials": True},
    )
    assert response.status_code == 201, response.text
    assert generator.calls[0][1] == [allowed]
    assert response.json()["source_context"]["evidence_count"] == 1

    approval = {"current": True}
    monkeypatch.setattr(main_module, "catalog", SimpleNamespace(
        externally_approved_document_ids=lambda ids: ids & {UUID(allowed.chunk.document_id)}
        if approval["current"] else set()))

    class RevokingUsage(_Usage):
        def reserve(self, **kwargs):
            reservation_id = super().reserve(**kwargs)
            approval["current"] = False
            return reservation_id

    usage = RevokingUsage()
    monkeypatch.setattr(main_module, "model_usage", usage)
    blocked_response = TestClient(main_module.app).post(
        "/api/v1/teaching-drafts/generate", headers={"Authorization": "Bearer teacher"},
        json={"course_id": str(course_id), "draft_type": "teaching_plan", "topic": "二叉树",
              "share_course_materials": True},
    )
    assert blocked_response.status_code == 409
    assert "未调用模型" in blocked_response.json()["detail"]
    assert len(generator.calls) == 1
    assert usage.finishes[0][1]["error_type"] == "ExternalApprovalRevoked"
    with sessions() as session:
        assert session.query(TeachingDraft).count() == 1
