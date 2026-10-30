from dataclasses import dataclass
import re

from app.domain import SearchHit
from app.vector_store import InMemoryVectorStore


@dataclass(frozen=True)
class RetrievalResult:
    accepted: bool
    message: str
    hits: list[SearchHit]


class RetrievalService:
    def __init__(self, store: InMemoryVectorStore, *, min_score: float, top_k: int) -> None:
        self._store = store
        self._min_score = min_score
        self._top_k = top_k

    def retrieve(self, question: str, knowledge_base_id: str | None = None, *, document_id: str | None = None) -> RetrievalResult:
        filters = {'knowledge_base_id': knowledge_base_id}
        if document_id is not None:
            filters['document_id'] = document_id
        hits = self._store.search(question, self._top_k, **filters)
        # Explicit compound questions often dilute one another in a single
        # multilingual embedding. Keep the original search and supplement at
        # most three independently written questions, using identical access
        # filters and the unchanged acceptance threshold. Never ask a model to
        # invent expansions or turn a weak unrelated passage into an answer.
        parts = self._question_parts(question)
        if parts:
            by_id = {hit.chunk.chunk_id: hit for hit in hits}
            for part in parts:
                for hit in self._store.search(part, self._top_k, **filters):
                    previous = by_id.get(hit.chunk.chunk_id)
                    if previous is None or hit.score > previous.score:
                        by_id[hit.chunk.chunk_id] = hit
            hits = sorted(by_id.values(), key=lambda hit: hit.score, reverse=True)[:self._top_k]
        accepted_hits = [hit for hit in hits if hit.score >= self._min_score]
        accepted = bool(accepted_hits)
        message = "已找到可用证据。" if accepted else "无法从当前课程资料中确定答案。"
        return RetrievalResult(accepted=accepted, message=message, hits=accepted_hits)

    @staticmethod
    def _question_parts(question: str) -> list[str]:
        if len(question) > 1200 or "```" in question:
            return []
        # Keep the user's question punctuation: multilingual embeddings can
        # change meaning/ranking when a natural question is turned into a stem.
        parts = [part.strip() for part in re.findall(r"[^?？]+(?:[?？]+|$)", question) if len(part.strip()) >= 4]
        if len(parts) < 2 or not re.search(r"[?？]", question):
            return []
        return list(dict.fromkeys(parts))[:3]
