from app.domain import TextChunk
from app.embedding import HashingEmbedder
from app.hybrid_store import HybridVectorStore, keyword_overlap


def _chunk(chunk_id: str, text: str) -> TextChunk:
    return TextChunk(chunk_id, "doc", "course.pdf", 1, text)


def test_keyword_overlap_rewards_exact_course_terms() -> None:
    assert keyword_overlap("后进先出", "栈是后进先出结构") > keyword_overlap("后进先出", "图的遍历包括深度优先")


def test_hybrid_store_returns_combined_score() -> None:
    store = HybridVectorStore(HashingEmbedder(), vector_weight=0.5)
    store.add([_chunk("one", "栈是后进先出的线性表。"), _chunk("two", "图的遍历包括深度优先。")])

    hits = store.search("后进先出", top_k=1)

    assert hits[0].chunk.chunk_id == "one"
    assert 0 <= hits[0].score <= 1
