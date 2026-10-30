import re
from hashlib import sha1

from app.domain import SourceDocument, TextChunk


_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?;；\n])")


def _stable_id(document_id: str, page_number: int, index: int, text: str) -> str:
    digest = sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{document_id}-p{page_number}-c{index}-{digest}"


def chunk_document(
    document: SourceDocument,
    *,
    chunk_size: int = 500,
    overlap: int = 80,
    structure_aware: bool = False,
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")
    if structure_aware:
        return _structured_chunks(document, chunk_size, overlap)

    normalized = re.sub(r"[ \t]+", " ", document.text).strip()
    if not normalized:
        return []

    sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(normalized) if part.strip()]
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) <= chunk_size:
            current += sentence
            continue
        if current:
            chunks.append(current)
            prefix = current[-overlap:] if overlap else ""
            current = prefix + sentence
        else:
            step = chunk_size - overlap
            chunks.extend(sentence[start : start + chunk_size] for start in range(0, len(sentence), step))
            current = ""
    if current:
        chunks.append(current)

    return [
        TextChunk(
            chunk_id=_stable_id(document.document_id, document.page_number, index, text),
            document_id=document.document_id,
            document_name=document.document_name,
            page_number=document.page_number,
            chapter=document.chapter,
            text=text,
        )
        for index, text in enumerate(chunks)
    ]


_PROTECTED = re.compile(r'```[^\n]*\n[\s\S]*?```|~~~[^\n]*\n[\s\S]*?~~~|\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|(?<!\$)\$(?!\$)[^\n$]+\$|\\\([^\n]*?\\\)')


def _structured_chunks(document, chunk_size, overlap):
    """Opt-in for NEW imports; old chunk IDs/vectors stay exactly as imported.

    Preserve fenced examples and explicit LaTeX as atomic units, break prose
    at paragraph/sentence boundaries, overlap whole units only. Does not infer
    equations from OCR or prove semantic topic segmentation.
    """
    text = document.text.strip()
    units, position = [], 0
    def prose(value):
        for paragraph in re.split(r'\n\s*\n', value):
            for sentence in _SENTENCE_BOUNDARY.split(paragraph):
                sentence = sentence.strip()
                if sentence:
                    # Hard cap for unstructured continuous text; protected spans never enter here.
                    units.extend(sentence[i:i+chunk_size] for i in range(0, len(sentence), chunk_size))
    for match in _PROTECTED.finditer(text):
        prose(text[position:match.start()])
        if len(match[0]) > max(4000, chunk_size * 4):
            raise ValueError('单个公式或代码块过长，请先按完整示例拆分后导入。')
        units.append(match[0]); position = match.end()
    prose(text[position:])
    chunks, current = [], []
    for unit in units:
        size = sum(len(u) + 1 for u in current) + len(unit)
        heading = bool(re.match(r'^#{1,6}\s', unit))
        if current and (size > chunk_size or heading):
            chunks.append('\n'.join(current))
            tail, count = [], 0
            if not heading:
                for part in reversed(current):
                    if count + len(part) + 1 > overlap: break
                    tail.insert(0, part); count += len(part) + 1
            current = tail
        current.append(unit)
    if current: chunks.append('\n'.join(current))
    return [TextChunk(chunk_id=_stable_id(document.document_id, document.page_number, i, value),
        document_id=document.document_id, document_name=document.document_name, page_number=document.page_number,
        chapter=document.chapter, text=value, metadata={'chunk_strategy': 'structure-v1'}) for i, value in enumerate(chunks)]
