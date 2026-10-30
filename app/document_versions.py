from uuid import UUID
from sqlalchemy import select
from app.models import Document, DocumentVersion, DocumentIngestionJob, AuditLog
from app.document_content import capture, replace
from app.pagination import sql_page

class DocumentVersionService:
    def __init__(self,sessions):self.sessions=sessions
    @staticmethod
    def brief(v):return dict(revision=v.revision,filename=v.filename,page_count=len(v.pages),has_pdf=bool(v.source_payload),created_at=v.created_at,preprocessing=v.preprocessing)
    def list(self,docid,page,page_size):
        with self.sessions() as s:
            doc=s.get(Document,docid)
            if not doc:raise LookupError('资料不存在。')
            result=sql_page(s,select(DocumentVersion).where(DocumentVersion.document_id==docid).order_by(DocumentVersion.revision.desc()),page=page,page_size=page_size,mapper=self.brief)
            return {**result,'current_revision':doc.content_revision}
    def get(self,docid,revision):
        with self.sessions() as s:
            v=s.scalar(select(DocumentVersion).where(DocumentVersion.document_id==docid,DocumentVersion.revision==revision))
            if not v:raise LookupError('版本不存在。')
            return v
    def restore(self,docid,revision,expected,actor):
        with self.sessions.begin() as s:
            doc=s.scalar(select(Document).where(Document.id==docid).with_for_update())
            if not doc:raise LookupError('资料不存在。')
            if doc.content_revision!=expected:raise ValueError('资料已经更新，请刷新版本记录。')
            if revision==doc.content_revision:raise ValueError('该版本已经是当前内容。')
            if s.scalar(select(DocumentIngestionJob.id).where(DocumentIngestionJob.document_id==docid,DocumentIngestionJob.status.in_(('queued','processing')))):
                raise ValueError('此资料仍有处理任务，请先完成或取消。')
            v=s.scalar(select(DocumentVersion).where(DocumentVersion.document_id==docid,DocumentVersion.revision==revision))
            if not v or not v.chunks:raise ValueError('此版本没有可恢复的索引内容。')
            capture(s,doc)
            replace(s,doc,v.pages,v.chunks)
            doc.content_revision+=1;doc.external_model_allowed=False
            created=capture(s,doc,payload=v.source_payload,preprocessing={**v.preprocessing,'restored_from':revision},creator_id=UUID(actor.id))
            s.add(AuditLog(actor_id=UUID(actor.id),actor_name=actor.display_name,action='restore',resource_type='document',resource_id=str(docid),detail=dict(from_revision=revision,new_revision=doc.content_revision)))
            return {**self.brief(created),'current_revision':doc.content_revision}
