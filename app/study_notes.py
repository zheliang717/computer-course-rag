"""Student-only notes that verify excerpts against accessible published pages."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models import Chunk, Course, CourseEnrollment, CourseKnowledgeBase, Document, DocumentPage, StudyNote
from app.pagination import sql_page


class StudyNoteService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _page_content(session, *, document_id: UUID, page_number: int) -> str | None:
        page = session.scalar(select(DocumentPage).where(
            DocumentPage.document_id == document_id, DocumentPage.page_number == page_number,
        ))
        if page is not None:
            return page.content
        # Older imports have indexed chunks but no persisted PDF page row.
        chunks = session.scalars(select(Chunk.content).where(
            Chunk.document_id == document_id, Chunk.page_number == page_number,
        ).order_by(Chunk.position)).all()
        return "\n\n".join(chunks) if chunks else None

    @staticmethod
    def _source_available(session, note: StudyNote) -> bool:
        if note.document_id is None:
            return False
        document = session.get(Document, note.document_id)
        return bool(document and document.publication_status == "published" and session.scalar(
            select(CourseKnowledgeBase.id).where(
                CourseKnowledgeBase.course_id == note.course_id,
                CourseKnowledgeBase.knowledge_base_id == document.knowledge_base_id,
            )
        ) and StudyNoteService._page_content(
            session, document_id=note.document_id, page_number=note.page_number,
        ))

    def _item(self, session, note: StudyNote) -> dict:
        course = session.get(Course, note.course_id)
        return {
            "id": str(note.id), "course_id": str(note.course_id),
            "course_title": course.title if course else "课程已移除",
            "document_id": str(note.document_id) if note.document_id else None,
            "source_title": note.source_title, "page_number": note.page_number,
            "excerpt": note.excerpt, "content": note.content, "origin": note.origin,
            "source_available": self._source_available(session, note),
            "created_at": note.created_at,
        }

    def create(self, *, student_id: UUID, course_id: UUID, document_id: UUID,
               page_number: int, excerpt: str, content: str, origin: str) -> dict | None:
        with self._session_factory() as session:
            enrolled = session.scalar(select(CourseEnrollment.id).where(
                CourseEnrollment.user_id == student_id,
                CourseEnrollment.course_id == course_id,
                CourseEnrollment.status == "active",
            ))
            document = session.get(Document, document_id)
            if not enrolled or not document or document.publication_status != "published":
                return None
            linked = session.scalar(select(CourseKnowledgeBase.id).where(
                CourseKnowledgeBase.course_id == course_id,
                CourseKnowledgeBase.knowledge_base_id == document.knowledge_base_id,
            ))
            page_content = self._page_content(session, document_id=document_id, page_number=page_number)
            if not linked or page_content is None:
                return None
            normalized_excerpt = self._normalize(excerpt)
            if len(normalized_excerpt) < 10 or not content.strip():
                raise ValueError("请选择至少 10 个字的原文并填写笔记内容。")
            if normalized_excerpt not in self._normalize(page_content):
                raise ValueError("摘录内容与所选资料页不一致，请重新选择原文。")
            note = StudyNote(
                student_id=student_id, course_id=course_id, document_id=document_id,
                source_title=document.filename, page_number=page_number,
                excerpt=excerpt.strip(), content=content.strip(), origin=origin,
            )
            session.add(note)
            session.commit()
            session.refresh(note)
            return self._item(session, note)

    def list_current(self, *, student_id: UUID, course_id: UUID | None = None,
                     page: int | None = None, page_size: int = 10) -> list[dict] | dict:
        with self._session_factory() as session:
            query = select(StudyNote).join(
                CourseEnrollment, (CourseEnrollment.course_id == StudyNote.course_id)
                & (CourseEnrollment.user_id == StudyNote.student_id)
            ).where(
                StudyNote.student_id == student_id, CourseEnrollment.status == "active",
            ).order_by(StudyNote.created_at.desc(), StudyNote.id.desc())
            if course_id:
                query = query.where(StudyNote.course_id == course_id)
            if page is not None:
                return sql_page(session, query, page=page, page_size=page_size,
                                mapper=lambda note: self._item(session, note))
            notes = session.scalars(query).all()
            return [self._item(session, note) for note in notes]

    def delete(self, *, student_id: UUID, note_id: UUID) -> bool:
        with self._session_factory() as session:
            note = session.get(StudyNote, note_id)
            if note is None or note.student_id != student_id:
                return False
            session.delete(note)
            session.commit()
            return True
