from app.domain import TextChunk
from app.embedding import HashingEmbedder
from app.rag import RetrievalService
from app.vector_store import InMemoryVectorStore


def _chunk(chunk_id: str, text: str, page: int) -> TextChunk:
    return TextChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        document_name="数据结构.pdf",
        page_number=page,
        text=text,
    )


def test_retrieval_returns_citation_for_related_question() -> None:
    store = InMemoryVectorStore(HashingEmbedder())
    store.add([
        _chunk("c1", "队列遵循先进先出原则，队头出队，队尾入队。", 8),
        _chunk("c2", "二叉搜索树的左子树键值小于根节点。", 20),
    ])
    service = RetrievalService(store, min_score=0.05, top_k=1)

    result = service.retrieve("队列遵循什么原则？")

    assert result.accepted is True
    assert result.hits[0].chunk.page_number == 8


def test_retrieval_refuses_when_knowledge_base_is_empty() -> None:
    service = RetrievalService(InMemoryVectorStore(HashingEmbedder()), min_score=0.1, top_k=5)

    result = service.retrieve("什么是图？")

    assert result.accepted is False
    assert result.hits == []
