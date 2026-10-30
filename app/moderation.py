from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select

from app.catalog import stable_document_uuid
from app.models import Chunk, Document, KnowledgeBase, QuestionRecord, QuestionReview, User, AnswerFeedbackAnnotation
from app.pagination import sql_page


class QuestionModerationService:
    """Review AI answers and optionally turn approved answers into RAG evidence."""

    def __init__(self, session_factory, embedder) -> None:
        self._session_factory = session_factory
        self._embedder = embedder

    @staticmethod
    def _item(record: QuestionRecord, review: QuestionReview | None, reviewer_name: str | None) -> dict:
        return {
            "id": str(record.id),
            "knowledge_base_id": str(record.knowledge_base_id) if record.knowledge_base_id else None,
            "question": record.question,
            "answer": record.answer,
            "message": record.message,
            "model": record.model,
            "accepted": record.accepted,
            "citations": list(record.citations or []),
            "rating": record.rating,
            "feedback": record.feedback,
            "created_at": record.created_at,
            "review_status": review.status if review else "pending",
            "revised_answer": review.revised_answer if review else None,
            "review_note": review.review_note if review else None,
            "reviewer_name": reviewer_name,
            "published_document_id": str(review.published_document_id) if review and review.published_document_id else None,
            "reviewed_at": review.reviewed_at if review else None,
        }

    def list(self, *, status: str | None = None, limit: int = 100,
             allowed_knowledge_base_ids: set[UUID] | None = None,
             page: int | None = None, page_size: int = 10, access=None) -> list[dict] | dict:
        statement = (
            select(QuestionRecord, QuestionReview, User.display_name)
            .outerjoin(QuestionReview, QuestionReview.question_record_id == QuestionRecord.id)
            .outerjoin(User, User.id == QuestionReview.reviewer_id)
            .order_by(QuestionRecord.created_at.desc(), QuestionRecord.id.desc())
        )
        if status == "pending":
            statement = statement.where(QuestionReview.id.is_(None))
        elif status == "feedback":
            statement = statement.where(select(1).where(AnswerFeedbackAnnotation.history_id==QuestionRecord.id).exists())
        elif status in {"approved", "rejected"}:
            statement = statement.where(QuestionReview.status == status)
        if allowed_knowledge_base_ids is not None:
            statement = statement.where(QuestionRecord.knowledge_base_id.in_(allowed_knowledge_base_ids))
        if access is not None:
            statement = statement.where(access.predicate(owner=False, review=True))
        with self._session_factory() as session:
            if page is not None:
                return sql_page(session, statement, page=page, page_size=page_size,
                                mapper=lambda row: self._item(*row), scalar=False)
            return [self._item(record, review, reviewer_name) for record, review, reviewer_name in session.execute(statement.limit(limit))]

    def review(
        self,
        record_id: UUID,
        *,
        reviewer_id: UUID | None,
        status: str,
        revised_answer: str | None,
        review_note: str | None,
        publish: bool,
        allowed_knowledge_base_ids: set[UUID] | None = None,
        access=None,
    ) -> dict | None:
        with self._session_factory() as session:
            statement = select(QuestionRecord).where(QuestionRecord.id == record_id)
            if access is not None:
                statement = statement.where(access.predicate(owner=False, review=True))
            record = session.scalar(statement.with_for_update())
            if record is None or (allowed_knowledge_base_ids is not None
                                  and record.knowledge_base_id not in allowed_knowledge_base_ids):
                return None
            if publish and (status != "approved" or record.knowledge_base_id is None):
                raise ValueError("只有关联知识库的已通过回答才能沉淀为课程资料。")

            review = session.scalar(select(QuestionReview).where(QuestionReview.question_record_id == record_id))
            if review is None:
                review = QuestionReview(question_record_id=record_id)
                session.add(review)
            review.reviewer_id = reviewer_id
            review.status = status
            review.revised_answer = revised_answer.strip() if revised_answer and revised_answer.strip() else None
            review.review_note = review_note.strip() if review_note and review_note.strip() else None

            # A previously curated answer must not remain searchable after a
            # teacher rejects it during a later review.
            if status == "rejected" and review.published_document_id:
                published_document = session.get(Document, review.published_document_id)
                if published_document is not None:
                    session.delete(published_document)
                review.published_document_id = None

            if publish:
                knowledge_base = session.get(KnowledgeBase, record.knowledge_base_id)
                if knowledge_base is None:
                    raise ValueError("问答关联的知识库不存在。")
                answer = review.revised_answer or record.answer
                content = f"问题：{record.question}\n\n教师精选解答：\n{answer}"
                document_id = stable_document_uuid(f"curated-answer-{record.id}")
                document = session.get(Document, document_id)
                filename = f"教师精选问答：{record.question[:30]}"
                if document is None:
                    document = Document(
                        id=document_id,
                        knowledge_base_id=knowledge_base.id,
                        filename=filename,
                        status="ready",
                        page_count=1,
                    )
                    session.add(document)
                    session.flush()
                else:
                    document.filename = filename
                    document.status = "ready"
                    document.page_count = 1
                    document.error_message = None
                    session.execute(delete(Chunk).where(Chunk.document_id == document_id))
                vector = self._embedder.embed([content])[0]
                session.add(Chunk(
                    document_id=document_id,
                    page_number=1,
                    chapter="教师精选问答",
                    position=0,
                    content=content,
                    content_metadata={"source": "question_review", "question_record_id": str(record.id)},
                    embedding=vector,
                ))
                review.published_document_id = document_id

            session.commit()
            session.refresh(review)
            reviewer_name = session.scalar(select(User.display_name).where(User.id == reviewer_id)) if reviewer_id else None
            return self._item(record, review, reviewer_name)
