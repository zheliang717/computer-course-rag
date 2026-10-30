from uuid import uuid4

import pytest
from fastapi import HTTPException

from app import main as main_module
from app.auth import Principal
from app.domain import SearchHit, TextChunk
from app.rag import RetrievalResult
from app.schemas import RetrieveRequest


def test_retrieval_uses_only_enrolled_course_bases(monkeypatch) -> None:
    own_base, other_base = uuid4(), uuid4()
    student = Principal(id=str(uuid4()), username="learner", display_name="Learner", role="student")

    class FakeAnalytics:
        def accessible_knowledge_base_ids(self, *, user_id, role):
            assert user_id == student.id or str(user_id) == student.id
            assert role == "student"
            return {own_base}

    class FakeRetrieval:
        def __init__(self):
            self.searched = []

        def retrieve(self, question, knowledge_base_id=None):
            self.searched.append(knowledge_base_id)
            chunk = TextChunk(
                chunk_id="own-chunk", document_id="own-doc", document_name="Course Notes",
                page_number=1, text=question,
            )
            return RetrievalResult(True, "found", [SearchHit(chunk=chunk, score=0.9)])

    fake_retrieval = FakeRetrieval()
    monkeypatch.setattr(main_module, "catalog", object())
    monkeypatch.setattr(main_module, "analytics", FakeAnalytics())
    monkeypatch.setattr(main_module, "retrieval", fake_retrieval)

    response = main_module.retrieve(RetrieveRequest(question="What is a stack?"), user=student)
    assert response.accepted
    assert len(response.citations) == 1
    assert fake_retrieval.searched == [str(own_base)]

    with pytest.raises(HTTPException) as error:
        main_module.retrieve(
            RetrieveRequest(question="What is a stack?", knowledge_base_id=str(other_base)),
            user=student,
        )
    assert error.value.status_code == 404
    assert fake_retrieval.searched == [str(own_base)]
