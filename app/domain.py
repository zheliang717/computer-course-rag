from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    document_name: str
    page_number: int
    text: str
    chapter: str | None = None


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    document_id: str
    document_name: str
    page_number: int
    text: str
    chapter: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchHit:
    chunk: TextChunk
    score: float
