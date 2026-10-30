from collections import defaultdict
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.catalog import DEFAULT_KNOWLEDGE_BASE_ID, stable_document_uuid
from app.database import Base
from app.domain import SearchHit, TextChunk
from app.embedding import Embedder
from app.hybrid_store import keyword_overlap
from app.models import Chunk, Document


class PgVectorStore:
    """PostgreSQL/pgvector implementation of the retrieval store contract.

    The public ``add``/``search`` methods mirror the in-memory store so the API
    can switch persistence backends without changing its routes. Incoming
    document ids are kept stable even when callers use human-readable ids
    rather than UUIDs.
    """

    _default_knowledge_base_id = DEFAULT_KNOWLEDGE_BASE_ID
    _lexical_rescue_floor = 0.5
    _lexical_rescue_cap = 0.12
    _lexical_rescue_min_han_chars = 10
    _lexical_rescue_max_vector_score = 0.5

    def __init__(self, session_factory: Callable[[], Session], embedder: Embedder, *, vector_weight: float = 0.7) -> None:
        if not 0 <= vector_weight <= 1:
            raise ValueError("vector_weight must be between 0 and 1")
        self._session_factory = session_factory
        self._embedder = embedder
        self._vector_weight = vector_weight

    def set_vector_weight(self, value: float) -> None:
        if not 0 <= value <= 1:
            raise ValueError("vector_weight must be between 0 and 1")
        self._vector_weight = value

    @classmethod
    def _candidate_score(cls, vector_score: float, keyword_score: float, vector_weight: float,
                         *, lexical_rescue: bool = True) -> float:
        score = vector_weight * vector_score + (1 - vector_weight) * keyword_score
        if (lexical_rescue and 0 < vector_weight < 1
                and vector_score < cls._lexical_rescue_max_vector_score):
            # An exact course phrase can sit outside the original vector
            # window. Already strong vector hits need no lift; cap the
            # remainder so common query words cannot dominate.
            score += min(cls._lexical_rescue_cap, max(0.0, keyword_score - cls._lexical_rescue_floor))
        return min(1.0, score)

    @classmethod
    def _supports_lexical_rescue(cls, query: str) -> bool:
        # Short questions such as "什么是虚拟内存" give too little context for
        # an exact-word lift to safely reorder otherwise strong evidence.
        return sum("\u4e00" <= char <= "\u9fff" for char in query) >= cls._lexical_rescue_min_han_chars

    def create_schema(self, engine) -> None:
        Base.metadata.create_all(engine)

    @property
    def size(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count(Chunk.id))) or 0)

    @staticmethod
    def _document_uuid(document_id: str | UUID) -> UUID:
        return stable_document_uuid(document_id)

    def _ensure_document(self, session: Session, document_id: str, document_name: str) -> Document:
        resolved_id = self._document_uuid(document_id)
        document = session.get(Document, resolved_id)
        if document is None:
            from app.models import KnowledgeBase

            knowledge_base = session.get(KnowledgeBase, self._default_knowledge_base_id)
            if knowledge_base is None:
                knowledge_base = KnowledgeBase(
                    id=self._default_knowledge_base_id,
                    name="计算机课程资料库",
                    course="计算机基础",
                    description="由 RAG 原型导入的课程资料。",
                )
                session.add(knowledge_base)
                session.flush()
            document = Document(
                id=resolved_id,
                knowledge_base_id=knowledge_base.id,
                filename=document_name,
                status="pending",
            )
            session.add(document)
            session.flush()
        else:
            document.filename = document_name
        return document

    def add(self, chunks: list[TextChunk]) -> int:
        if not chunks:
            return 0

        grouped: dict[str, list[TextChunk]] = defaultdict(list)
        for chunk in chunks:
            grouped[chunk.document_id].append(chunk)

        with self._session_factory() as session:
            for external_id, document_chunks in grouped.items():
                first = document_chunks[0]
                document = self._ensure_document(session, external_id, first.document_name)
                session.execute(delete(Chunk).where(Chunk.document_id == document.id))
                vectors = self._embedder.embed([chunk.text for chunk in document_chunks])
                for position, (chunk, vector) in enumerate(zip(document_chunks, vectors, strict=True)):
                    session.add(
                        Chunk(
                            document_id=document.id,
                            page_number=chunk.page_number,
                            chapter=chunk.chapter,
                            position=position,
                            content=chunk.text,
                            content_metadata=chunk.metadata,
                            embedding=vector,
                        )
                    )
                document.page_count = max(chunk.page_number for chunk in document_chunks)
                document.status = "ready"
                document.error_message = None
            session.commit()
        return len(chunks)

    def add_chunks(self, document_id: UUID, chunks: list[TextChunk]) -> int:
        """Backward-compatible explicit-document helper for ingestion callers."""
        if not chunks:
            return 0
        with self._session_factory() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise ValueError(f"Document not found: {document_id}")
        return self.add(chunks)

    def prepare_vectors(self, chunks):
        """Compute before taking content locks; publication owns its transaction."""
        return [list(map(float,v)) for v in self._embedder.embed([c.text for c in chunks])]

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        knowledge_base_id: str | UUID | None = None,
        document_id: str | UUID | None = None,
    ) -> list[SearchHit]:
        if not query.strip() or top_k <= 0:
            return []
        parsed_knowledge_base_id: UUID | None = None
        if knowledge_base_id is not None:
            try:
                parsed_knowledge_base_id = UUID(str(knowledge_base_id))
            except ValueError:
                return []
        vector = self._embedder.embed([query])[0]
        lexical_rescue = self._supports_lexical_rescue(query) and 0 < self._vector_weight < 1
        distance = Chunk.embedding.cosine_distance(vector)
        # Preserve the original candidate window and scores. Extra candidates
        # may be rescued, but must not reshuffle matches already in that window.
        legacy_candidate_limit = max(top_k * 8, top_k)
        candidate_limit = (max(legacy_candidate_limit, min(top_k * 16, 160))
                           if lexical_rescue else legacy_candidate_limit)
        statement: Select[tuple[Chunk, Document, object]] = (
            select(Chunk, Document, distance.label("distance"))
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.embedding.is_not(None), Document.publication_status == "published", Document.status == "ready")
        )
        if parsed_knowledge_base_id is not None:
            statement = statement.where(Document.knowledge_base_id == parsed_knowledge_base_id)
        if document_id is not None:
            statement = statement.where(Document.id == UUID(str(document_id)))
        statement = statement.order_by(distance).limit(candidate_limit)
        with self._session_factory() as session:
            rows = session.execute(statement).all()
        hits: list[SearchHit] = []
        for candidate_index, (row, document, row_distance) in enumerate(rows):
            vector_score = max(0.0, 1.0 - float(row_distance))
            keyword_score = keyword_overlap(query, row.content)
            score = self._candidate_score(vector_score, keyword_score, self._vector_weight,
                                          lexical_rescue=lexical_rescue
                                          and candidate_index >= legacy_candidate_limit)
            hits.append(
                SearchHit(
                    chunk=TextChunk(
                        chunk_id=str(row.id),
                        document_id=str(row.document_id),
                        document_name=document.filename,
                        page_number=row.page_number,
                        text=row.content,
                        chapter=row.chapter,
                        metadata=row.content_metadata,
                    ),
                    score=score,
                )
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]
