import re
from collections import Counter

from app.domain import SearchHit, TextChunk
from app.embedding import Embedder
from app.vector_store import cosine_similarity


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    words = re.findall(r"[a-z0-9_]+", lowered)
    chinese = re.findall(r"[\u4e00-\u9fff]", lowered)
    bigrams = ["".join(chinese[i : i + 2]) for i in range(len(chinese) - 1)]
    return words + chinese + bigrams


def keyword_overlap(query: str, text: str) -> float:
    query_tokens = Counter(_tokens(query))
    document_tokens = Counter(_tokens(text))
    if not query_tokens or not document_tokens:
        return 0.0
    matched = sum(min(count, document_tokens[token]) for token, count in query_tokens.items())
    return min(1.0, matched / sum(query_tokens.values()))


class HybridVectorStore:
    """Portable hybrid baseline; production persistence is PgVectorStore."""

    def __init__(self, embedder: Embedder, *, vector_weight: float = 0.7) -> None:
        if not 0 <= vector_weight <= 1:
            raise ValueError("vector_weight must be between 0 and 1")
        self._embedder = embedder
        self._vector_weight = vector_weight
        self._records: list[tuple[TextChunk, list[float]]] = []

    def set_vector_weight(self, value: float) -> None:
        if not 0 <= value <= 1:
            raise ValueError("vector_weight must be between 0 and 1")
        self._vector_weight = value

    @property
    def size(self) -> int:
        return len(self._records)

    def add(self, chunks: list[TextChunk]) -> None:
        vectors = self._embedder.embed([chunk.text for chunk in chunks])
        self._records.extend(zip(chunks, vectors, strict=True))

    def search(self, query: str, top_k: int = 5, *, knowledge_base_id: str | None = None, document_id: str | None = None) -> list[SearchHit]:
        del knowledge_base_id  # The memory backend has no separate catalog.
        if not query.strip() or top_k <= 0 or not self._records:
            return []
        query_vector = self._embedder.embed([query])[0]
        hits = []
        for chunk, vector in self._records:
            if document_id is not None and chunk.document_id != document_id:
                continue
            vector_score = max(0.0, cosine_similarity(query_vector, vector))
            keyword_score = keyword_overlap(query, chunk.text)
            score = self._vector_weight * vector_score + (1 - self._vector_weight) * keyword_score
            hits.append(SearchHit(chunk=chunk, score=score))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]
