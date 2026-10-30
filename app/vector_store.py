from app.domain import SearchHit, TextChunk
from app.embedding import Embedder


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


class InMemoryVectorStore:
    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._records: list[tuple[TextChunk, list[float]]] = []

    @property
    def size(self) -> int:
        return len(self._records)

    def add(self, chunks: list[TextChunk]) -> None:
        vectors = self._embedder.embed([chunk.text for chunk in chunks])
        self._records.extend(zip(chunks, vectors, strict=True))

    def search(self, query: str, top_k: int = 5, *, knowledge_base_id: str | None = None, document_id: str | None = None) -> list[SearchHit]:
        del knowledge_base_id
        if not query.strip() or not self._records:
            return []
        query_vector = self._embedder.embed([query])[0]
        hits = [SearchHit(chunk=chunk, score=cosine_similarity(query_vector, vector)) for chunk, vector in self._records
                if document_id is None or chunk.document_id == document_id]
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]
