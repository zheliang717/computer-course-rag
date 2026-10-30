from collections.abc import Callable
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import AuditLog, Chunk, Document, DocumentPage, KnowledgeBase
from app.pagination import sql_page


DEFAULT_KNOWLEDGE_BASE_ID = uuid5(NAMESPACE_URL, "computer-course-rag/default-knowledge-base")


def stable_document_uuid(document_id: str | UUID) -> UUID:
    if isinstance(document_id, UUID):
        return document_id
    try:
        return UUID(str(document_id))
    except ValueError:
        return uuid5(NAMESPACE_URL, f"computer-course-rag/document/{document_id}")


class KnowledgeCatalog:
    """Small persistence service for knowledge-base and document metadata."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def ensure_default(self) -> KnowledgeBase:
        with self._session_factory() as session:
            knowledge_base = session.get(KnowledgeBase, DEFAULT_KNOWLEDGE_BASE_ID)
            if knowledge_base is None:
                knowledge_base = KnowledgeBase(
                    id=DEFAULT_KNOWLEDGE_BASE_ID,
                    name="计算机课程资料库",
                    course="计算机基础",
                    description="系统默认课程资料库。",
                )
                session.add(knowledge_base)
                session.commit()
            return knowledge_base

    def list_knowledge_bases(self) -> list[tuple[KnowledgeBase, int]]:
        statement = (
            select(KnowledgeBase, func.count(Document.id).label("document_count"))
            .outerjoin(Document, Document.knowledge_base_id == KnowledgeBase.id)
            .group_by(
                KnowledgeBase.id,
                KnowledgeBase.name,
                KnowledgeBase.course,
                KnowledgeBase.description,
                KnowledgeBase.created_at,
            )
            .order_by(KnowledgeBase.created_at, KnowledgeBase.name)
        )
        with self._session_factory() as session:
            return [(row[0], int(row[1])) for row in session.execute(statement).all()]

    def create_knowledge_base(self, *, name: str, course: str, description: str | None,
                              created_by: UUID | None = None) -> KnowledgeBase:
        with self._session_factory() as session:
            knowledge_base = KnowledgeBase(name=name, course=course, description=description, created_by=created_by)
            session.add(knowledge_base)
            session.commit()
            session.refresh(knowledge_base)
            return knowledge_base

    def update_knowledge_base(
        self,
        knowledge_base_id: UUID,
        *,
        name: str | None,
        course: str | None,
        description: str | None,
    ) -> KnowledgeBase | None:
        with self._session_factory() as session:
            knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
            if knowledge_base is None:
                return None
            if name is not None:
                knowledge_base.name = name
            if course is not None:
                knowledge_base.course = course
            if description is not None:
                knowledge_base.description = description
            session.commit()
            session.refresh(knowledge_base)
            return knowledge_base

    def delete_knowledge_base(self, knowledge_base_id: UUID, *, actor_id: UUID | None,
                              actor_name: str) -> bool:
        if knowledge_base_id == DEFAULT_KNOWLEDGE_BASE_ID:
            raise ValueError("默认资料库不能删除。")
        with self._session_factory() as session:
            knowledge_base = session.scalar(select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id).with_for_update())
            if knowledge_base is None:
                return False
            session.delete(knowledge_base)
            session.add(AuditLog(
                actor_id=actor_id, actor_name=actor_name, action="delete",
                resource_type="knowledge_base", resource_id=str(knowledge_base_id),
                detail={"name": knowledge_base.name, "confirmed": True},
            ))
            session.commit()
            return True

    def get_knowledge_base(self, knowledge_base_id: UUID) -> KnowledgeBase | None:
        with self._session_factory() as session:
            return session.get(KnowledgeBase, knowledge_base_id)

    def ensure_document(
        self,
        *,
        document_id: str,
        knowledge_base_id: UUID,
        filename: str,
        preserve_ready: bool = False,
    ) -> Document:
        resolved_id = stable_document_uuid(document_id)
        with self._session_factory() as session:
            if session.get(KnowledgeBase, knowledge_base_id) is None:
                raise LookupError("知识库不存在。")
            document = session.get(Document, resolved_id)
            if document is None:
                document = Document(
                    id=resolved_id,
                    knowledge_base_id=knowledge_base_id,
                    filename=filename,
                    status="pending",
                )
                session.add(document)
            elif document.knowledge_base_id != knowledge_base_id:
                raise ValueError("文档已经属于其他知识库。")
            elif not (preserve_ready and document.status == 'ready'):
                document.filename = filename
                document.status = "pending"
                document.error_message = None
                document.external_model_allowed = False
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                document=session.get(Document,resolved_id)
                if document is None:raise
                if document.knowledge_base_id!=knowledge_base_id:raise ValueError("文档已经属于其他知识库。")
            session.refresh(document)
            return document

    def mark_document_error(self, document_id: str, message: str) -> None:
        resolved_id = stable_document_uuid(document_id)
        with self._session_factory() as session:
            document = session.get(Document, resolved_id)
            if document is not None:
                document.status = "error"
                document.error_message = message
                session.commit()

    def list_documents(self, knowledge_base_id: UUID, *, published_only: bool = False,
                       page: int | None = None, page_size: int = 10) -> list[tuple[Document, int]] | dict:
        chunk_count = (
            select(func.count(Chunk.id))
            .where(Chunk.document_id == Document.id)
            .correlate(Document)
            .scalar_subquery()
        )
        statement = (
            select(Document, chunk_count.label("chunk_count"))
            .where(Document.knowledge_base_id == knowledge_base_id)
            .order_by(Document.created_at, Document.filename, Document.id)
        )
        if published_only:
            statement = statement.where(Document.publication_status == "published")
        with self._session_factory() as session:
            if page is not None:
                return sql_page(session, statement, page=page, page_size=page_size,
                                mapper=lambda row: (row[0], int(row[1])), scalar=False)
            return [(row[0], int(row[1])) for row in session.execute(statement).all()]

    def get_document(self, document_id: str | UUID) -> tuple[Document, int] | None:
        resolved_id = stable_document_uuid(document_id)
        chunk_count = (
            select(func.count(Chunk.id))
            .where(Chunk.document_id == resolved_id)
            .scalar_subquery()
        )
        statement = select(Document, chunk_count.label("chunk_count")).where(Document.id == resolved_id)
        with self._session_factory() as session:
            row = session.execute(statement).first()
            return (row[0], int(row[1])) if row else None

    def update_document(self, document_id: str | UUID, *, actor_id: UUID | None = None,
                        actor_name: str | None = None, **changes) -> tuple[Document, int] | None:
        resolved_id = stable_document_uuid(document_id)
        with self._session_factory() as session:
            document = session.scalar(select(Document).where(Document.id == resolved_id).with_for_update())
            if document is None:
                return None
            normalized = {}
            for key, value in changes.items():
                mapped_key = "filename" if key == "name" else key
                normalized[mapped_key] = value.strip() or None if isinstance(value, str) else value
            review_fields = {"source_url", "license_name", "license_url", "version_label", "publication_status"}
            changed_fields = sorted(key for key, value in normalized.items() if getattr(document, key) != value)
            if any(key in changed_fields for key in review_fields):
                document.external_model_allowed = False
            for key, value in normalized.items():
                setattr(document, key, value)
            if actor_name is not None:
                session.add(AuditLog(
                    actor_id=actor_id, actor_name=actor_name, action="update",
                    resource_type="document", resource_id=str(resolved_id),
                    detail={"changed_fields": changed_fields, "publication_status": document.publication_status,
                            "version_label": document.version_label,
                            "external_model_allowed": document.external_model_allowed},
                ))
            session.commit()
        return self.get_document(resolved_id)

    def externally_approved_document_ids(self, document_ids: set[UUID]) -> set[UUID]:
        if not document_ids:
            return set()
        with self._session_factory() as session:
            return set(session.scalars(
                select(Document.id).where(Document.id.in_(document_ids),
                                          Document.external_model_allowed.is_(True),
                                          Document.publication_status == "published",
                                          Document.status == "ready")
            ).all())

    def set_external_sharing(self, document_id: UUID, *, allowed: bool, reason: str,
                             actor_id: UUID, actor_name: str) -> tuple[Document, int] | None:
        with self._session_factory() as session:
            document = session.scalar(select(Document).where(Document.id == document_id).with_for_update())
            if document is None:
                return None
            if allowed and (not document.source_url or not document.license_name or not document.license_url or
                            document.publication_status != "published" or document.status != "ready"):
                raise ValueError("批准外发前须填写来源和许可信息，并确保资料已发布且索引就绪。")
            previous = document.external_model_allowed
            document.external_model_allowed = allowed
            session.add(AuditLog(
                actor_id=actor_id, actor_name=actor_name, action="approve_external_share" if allowed else "revoke_external_share",
                resource_type="document", resource_id=str(document_id),
                detail={"previous": previous, "allowed": allowed, "reason": reason.strip(),
                        "source_url": document.source_url, "license_name": document.license_name},
            ))
            session.commit()
        return self.get_document(document_id)

    def replace_pages(self, document_id: str | UUID, pages) -> None:
        resolved_id = stable_document_uuid(document_id)
        with self._session_factory() as session:
            session.execute(delete(DocumentPage).where(DocumentPage.document_id == resolved_id))
            session.add_all([
                DocumentPage(
                    document_id=resolved_id, page_number=page.page_number,
                    chapter=page.chapter, content=page.text,
                ) for page in pages
            ])
            session.commit()

    def get_document_content(self, document_id: str | UUID) -> tuple[tuple[Document, int], list[dict]] | None:
        resolved_id = stable_document_uuid(document_id)
        stored = self.get_document(resolved_id)
        if stored is None:
            return None
        with self._session_factory() as session:
            pages = list(session.scalars(
                select(DocumentPage).where(DocumentPage.document_id == resolved_id).order_by(DocumentPage.page_number)
            ).all())
            chunks = list(session.scalars(
                select(Chunk).where(Chunk.document_id == resolved_id).order_by(Chunk.page_number, Chunk.position)
            ).all())
            chunks_by_page: dict[int, list[Chunk]] = {}
            for chunk in chunks:
                chunks_by_page.setdefault(chunk.page_number, []).append(chunk)
            page_map = {page.page_number: page for page in pages}
            page_numbers = sorted(set(page_map) | set(chunks_by_page))
            result = []
            for number in page_numbers:
                page = page_map.get(number)
                page_chunks = chunks_by_page.get(number, [])
                result.append({
                    "page_number": number,
                    "chapter": page.chapter if page else (page_chunks[0].chapter if page_chunks else None),
                    "content": page.content if page else "\n\n".join(chunk.content for chunk in page_chunks),
                    "chunks": [{
                        "id": str(chunk.id), "page_number": chunk.page_number, "chapter": chunk.chapter,
                        "position": chunk.position, "content": chunk.content,
                    } for chunk in page_chunks],
                })
            return stored, result

    def delete_document(self, document_id: str | UUID, *, expected_knowledge_base_id: UUID,
                        actor_id: UUID | None, actor_name: str) -> bool:
        resolved_id = stable_document_uuid(document_id)
        with self._session_factory() as session:
            document = session.scalar(select(Document).where(Document.id == resolved_id).with_for_update())
            if document is None or document.knowledge_base_id != expected_knowledge_base_id:
                return False
            session.delete(document)
            session.add(AuditLog(
                actor_id=actor_id, actor_name=actor_name, action="delete",
                resource_type="document", resource_id=str(resolved_id),
                detail={"knowledge_base_id": str(document.knowledge_base_id),
                        "filename": document.filename, "confirmed": True},
            ))
            session.commit()
            return True
