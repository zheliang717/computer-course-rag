from app.chunking import chunk_document
from app.domain import SourceDocument


def test_chunk_document_preserves_source_metadata() -> None:
    source = SourceDocument(
        document_id="ds-1",
        document_name="数据结构.pdf",
        page_number=12,
        chapter="树",
        text="二叉树是每个节点最多有两个子树的树。遍历分为先序、中序和后序。",
    )

    chunks = chunk_document(source, chunk_size=24, overlap=4)

    assert len(chunks) >= 2
    assert all(chunk.document_name == "数据结构.pdf" for chunk in chunks)
    assert all(chunk.page_number == 12 for chunk in chunks)
    assert all(chunk.chapter == "树" for chunk in chunks)
