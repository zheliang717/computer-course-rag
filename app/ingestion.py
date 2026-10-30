from pathlib import Path

from app.chunking import chunk_document
from app.config import Settings
from app.domain import TextChunk
from app.pdf import extract_pdf_pages
from app.hybrid_store import HybridVectorStore


def index_pdf(
    path: str | Path,
    store: HybridVectorStore,
    *,
    document_id: str,
    document_name: str | None = None,
    settings: Settings | None = None,
) -> list[TextChunk]:
    """Extract a text PDF, preserve source pages, chunk it, and add it to a store."""
    settings = settings or Settings()
    pages = extract_pdf_pages(path, document_id=document_id, document_name=document_name)
    chunks = [
        chunk
        for page in pages
        for chunk in chunk_document(page, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
    ]
    store.add(chunks)
    return chunks
