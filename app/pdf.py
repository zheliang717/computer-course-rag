from pathlib import Path
from dataclasses import replace
import re
import pymupdf

from app.domain import SourceDocument


def extract_pdf_pages(path: str | Path, *, document_id: str, document_name: str | None = None) -> list[SourceDocument]:
    pdf_path = Path(path)
    name = document_name or pdf_path.name
    pages: list[SourceDocument] = []
    with pymupdf.open(pdf_path) as document:
        for index, page in enumerate(document):
            text = page.get_text("text", sort=True).strip()
            if text:
                pages.append(
                    SourceDocument(
                        document_id=document_id,
                        document_name=name,
                        page_number=index + 1,
                        text=text,
                    )
                )
    return pages


def extract_pdf_bytes(data: bytes, *, document_id: str, document_name: str) -> list[SourceDocument]:
    pages: list[SourceDocument] = []
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for index, page in enumerate(document):
            text = page.get_text("text", sort=True).strip()
            if text:
                pages.append(
                    SourceDocument(
                        document_id=document_id,
                        document_name=document_name,
                        page_number=index + 1,
                        text=text,
                    )
                )
    return pages

def prepare_pdf_pages(pages):
    """Conservative cleanup; original PDF bytes remain in immutable versions."""
    prepared=[];removed=0;chapters=0
    for page in pages:
        lines=page.text.splitlines();kept=[]
        for i,line in enumerate(lines):
            if (i<2 or i>=len(lines)-2) and re.fullmatch(r'\s*(?:第\s*)?\d{1,4}\s*(?:页|/\s*\d{1,4})?\s*',line) and len(lines)>4:
                removed+=1;continue
            kept.append(line)
        chapter=next((line.strip()[:200] for line in kept[:5] if re.match(r'^(?:第[一二三四五六七八九十百\d]+[章节]|Chapter\s+\d+)',line.strip(),re.I)),None)
        chapters+=int(chapter is not None)
        prepared.append(replace(page,text='\n'.join(kept).strip(),chapter=chapter or page.chapter))
    return prepared,dict(removed_page_number_lines=removed,chapter_heading_pages=chapters,policy='conservative-page-number-cleanup-v1')
