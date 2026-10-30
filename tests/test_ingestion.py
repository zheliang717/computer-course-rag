from pathlib import Path
import pymupdf as fitz

from app.embedding import HashingEmbedder
from app.ingestion import index_pdf
from app.vector_store import InMemoryVectorStore


def test_index_pdf_preserves_pages_and_indexes_generated_material(tmp_path: Path) -> None:
    source = tmp_path / 'original-four-page-fixture.pdf'
    with fitz.open() as pdf:
        for number in range(1, 5):
            page = pdf.new_page()
            page.insert_text((72, 72), f'Original test page {number}: a stack uses last-in-first-out order.')
        pdf.save(source)
    store = InMemoryVectorStore(HashingEmbedder())

    chunks = index_pdf(source, store, document_id="generated-demo", document_name="Original test material")

    assert len(chunks) > 0
    assert store.size == len(chunks)
    assert {chunk.page_number for chunk in chunks} == {1, 2, 3, 4}
