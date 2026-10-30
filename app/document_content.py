"""Atomic content publication; expensive parsing/embedding happens beforehand."""
from uuid import UUID, uuid4
from sqlalchemy import delete, select
from app.models import DocumentPage, Chunk, DocumentVersion
def capture(session, document, *, payload=None, preprocessing=None, creator_id=None):
    existing=session.scalar(select(DocumentVersion).where(DocumentVersion.document_id==document.id,DocumentVersion.revision==document.content_revision))
    if existing:return existing
    pages=session.scalars(select(DocumentPage).where(DocumentPage.document_id==document.id).order_by(DocumentPage.page_number)).all()
    chunks=session.scalars(select(Chunk).where(Chunk.document_id==document.id).order_by(Chunk.position)).all()
    version=DocumentVersion(document_id=document.id,revision=document.content_revision,filename=document.filename,
        pages=[dict(page_number=p.page_number,chapter=p.chapter,content=p.content) for p in pages],
        chunks=[dict(id=str(c.id),page_number=c.page_number,chapter=c.chapter,position=c.position,content=c.content,metadata=c.content_metadata,
            embedding=list(map(float,c.embedding)) if c.embedding is not None else None) for c in chunks],
        source_payload=payload,preprocessing=preprocessing or {},creator_id=creator_id)
    session.add(version);session.flush();return version
def replace(session, document, pages, chunks):
    session.execute(delete(DocumentPage).where(DocumentPage.document_id==document.id))
    session.execute(delete(Chunk).where(Chunk.document_id==document.id));session.flush()
    session.add_all([DocumentPage(document_id=document.id,**p) for p in pages])
    session.add_all([Chunk(id=UUID(c['id']) if c.get('id') else uuid4(),document_id=document.id,page_number=c['page_number'],
        chapter=c.get('chapter'),position=c['position'],content=c['content'],content_metadata=c.get('metadata',{}),embedding=c.get('embedding')) for c in chunks])
    document.page_count=max((p['page_number'] for p in pages),default=0)
    document.status='ready';document.error_message=None;session.flush()
