from __future__ import annotations
from datetime import datetime, timezone, timedelta
from threading import Event, Thread
from uuid import UUID, uuid4
from sqlalchemy import select, update, or_, func
from app.catalog import stable_document_uuid
from app.chunking import chunk_document
from app.models import AuditLog, Document, DocumentIngestionJob, Chunk
from app.pdf import extract_pdf_bytes, prepare_pdf_pages
from app.pagination import sql_page
from app.document_content import capture, replace

def now():return datetime.now(timezone.utc)
def utc(t):return t.replace(tzinfo=timezone.utc) if t and not t.tzinfo else t

class DocumentIngestionService:
    LEASE_SECONDS=120
    def __init__(self, session_factory, catalog, store, *, chunk_size, chunk_overlap):
        self._session_factory=session_factory;self._catalog=catalog;self._store=store
        self._chunk_size=chunk_size;self._chunk_overlap=chunk_overlap

    @staticmethod
    def _dict(job):
        return {key:getattr(job,key) for key in ('filename','status','progress_percent','attempts','page_count','chunk_count','error_message','created_at','started_at','finished_at')} | {
            'id':str(job.id),'knowledge_base_id':str(job.knowledge_base_id),'document_id':str(job.document_id)}

    def create(self, *, knowledge_base_id, document_key, filename, content_type, payload, creator_id):
        identifier=stable_document_uuid(document_key)
        self._catalog.ensure_document(document_id=document_key,knowledge_base_id=knowledge_base_id,filename=filename,preserve_ready=True)
        with self._session_factory.begin() as s:
            doc=s.scalar(select(Document).where(Document.id==identifier).with_for_update())
            active=s.scalar(select(DocumentIngestionJob.id).where(DocumentIngestionJob.document_id==identifier,DocumentIngestionJob.status.in_(('queued','processing'))))
            if active:raise ValueError('此资料已有处理任务，请等待完成或先取消。')
            job=DocumentIngestionJob(knowledge_base_id=knowledge_base_id,document_id=identifier,creator_id=creator_id,filename=filename,
                content_type=content_type,source_payload=payload,status='queued',progress_percent=0,base_revision=doc.content_revision)
            s.add(job);s.flush();return self._dict(job)

    def list(self, *, knowledge_base_id=None, limit=100, allowed_knowledge_base_ids=None, page=None, page_size=10):
        q=select(DocumentIngestionJob).order_by(DocumentIngestionJob.created_at.desc(),DocumentIngestionJob.id.desc())
        if knowledge_base_id is not None:q=q.where(DocumentIngestionJob.knowledge_base_id==knowledge_base_id)
        if allowed_knowledge_base_ids is not None:q=q.where(DocumentIngestionJob.knowledge_base_id.in_(allowed_knowledge_base_ids))
        with self._session_factory() as s:
            return sql_page(s,q,page=page,page_size=page_size,mapper=self._dict) if page is not None else [self._dict(j) for j in s.scalars(q.limit(limit))]

    def get(self,job_id):
        with self._session_factory() as s:
            j=s.get(DocumentIngestionJob,job_id);return self._dict(j) if j else None

    def retry(self,job_id,*,actor_id=None,actor_name=None):
        with self._session_factory.begin() as s:return self.retry_in_session(s,job_id,actor_id=actor_id,actor_name=actor_name)

    @classmethod
    def retry_in_session(cls,s,job_id,*,actor_id=None,actor_name=None,reason='用户手动重试',confirmed=False,operation_id=None):
        lookup=s.get(DocumentIngestionJob,job_id)
        if not lookup:return None
        doc=s.scalar(select(Document).where(Document.id==lookup.document_id).with_for_update())
        j=s.scalar(select(DocumentIngestionJob).where(DocumentIngestionJob.id==job_id).with_for_update().execution_options(populate_existing=True))
        expired=j.status=='processing' and (not j.lease_until or utc(j.lease_until)<=now())
        if j.status not in ('failed','cancelled') and not expired:raise ValueError('只有失败、已取消或中断的任务可以重试。')
        if not j.source_payload:raise ValueError('原始文件已不可用，请重新上传。')
        if s.scalar(select(DocumentIngestionJob.id).where(DocumentIngestionJob.document_id==j.document_id,DocumentIngestionJob.id!=j.id,DocumentIngestionJob.status.in_(('queued','processing')))):
            raise ValueError('此资料已有其他处理任务。')
        j.status='queued';j.progress_percent=0;j.error_message=None;j.started_at=None;j.finished_at=None;j.lease_token=None;j.lease_until=None;j.base_revision=doc.content_revision
        if actor_name:s.add(AuditLog(actor_id=actor_id,actor_name=actor_name,action='retry',resource_type='document_ingestion',resource_id=str(job_id),detail=dict(reason=reason,confirmed=confirmed,**({'assistant_operation_id':operation_id} if operation_id else {}))))
        return cls._dict(j)

    def cancel(self,job_id,*,actor_id,actor_name):
        with self._session_factory.begin() as s:
            lookup=s.get(DocumentIngestionJob,job_id)
            if not lookup:return None
            s.scalar(select(Document).where(Document.id==lookup.document_id).with_for_update())
            j=s.scalar(select(DocumentIngestionJob).where(DocumentIngestionJob.id==job_id).with_for_update().execution_options(populate_existing=True))
            if j.status=='completed':raise ValueError('任务已完成，请查看资料或版本记录。')
            j.status='cancelled';j.lease_token=None;j.lease_until=None;j.finished_at=now();j.error_message='已停止处理，原有资料保持可用。'
            s.add(AuditLog(actor_id=actor_id,actor_name=actor_name,action='cancel',resource_type='document_ingestion',resource_id=str(j.id),detail={}))
            return self._dict(j)

    def recover(self):
        with self._session_factory.begin() as s:
            expired=s.scalars(select(DocumentIngestionJob).where(DocumentIngestionJob.status=='processing',or_(DocumentIngestionJob.lease_until.is_(None),DocumentIngestionJob.lease_until<now())).with_for_update(skip_locked=True)).all()
            for j in expired:
                j.status='queued' if j.source_payload and j.attempts<3 else 'failed'
                j.lease_token=None;j.lease_until=None;j.error_message='处理中断，正在恢复。' if j.status=='queued' else '任务多次中断，请核对后重试。'
            return len(expired)

    def pending(self):
        with self._session_factory() as s:return s.scalar(select(DocumentIngestionJob.id).where(DocumentIngestionJob.status=='queued').order_by(DocumentIngestionJob.created_at).limit(1))

    def publish_pages(self,*,document_key,knowledge_base_id,filename,pages,chunks,creator_id,metadata=None,actor_name=''):
        doc=self._catalog.ensure_document(document_id=document_key,knowledge_base_id=knowledge_base_id,filename=filename,preserve_ready=True)
        expected=doc.content_revision;vectors=self._store.prepare_vectors(chunks)
        with self._session_factory.begin() as s:
            doc=s.scalar(select(Document).where(Document.id==doc.id).with_for_update())
            if doc.content_revision!=expected:raise ValueError('资料已经更新，请重新核对后导入。')
            if s.scalar(select(DocumentIngestionJob.id).where(DocumentIngestionJob.document_id==doc.id,DocumentIngestionJob.status.in_(('queued','processing')))):
                raise ValueError('资料仍有处理任务，请先完成或取消。')
            if doc.status=='ready':capture(s,doc)
            replace(s,doc,[dict(page_number=p.page_number,chapter=p.chapter,content=p.text) for p in pages],
                [dict(page_number=c.page_number,chapter=c.chapter,position=i,content=c.text,metadata=c.metadata,embedding=v) for i,(c,v) in enumerate(zip(chunks,vectors,strict=True))])
            doc.content_revision+=1;doc.filename=filename;doc.external_model_allowed=False
            for key,value in (metadata or {}).items():setattr(doc,key,value)
            capture(s,doc,creator_id=creator_id,preprocessing=dict(content_type='text/plain'))
            s.add(AuditLog(actor_id=creator_id,actor_name=actor_name or str(creator_id or 'system'),action='update',resource_type='document',resource_id=str(doc.id),detail=dict(content_revision=doc.content_revision,changed_fields=sorted((metadata or {}).keys()))))
            return doc.id

    def process(self,job_id):
        token=uuid4()
        with self._session_factory.begin() as s:
            lookup=s.get(DocumentIngestionJob,job_id)
            if not lookup:return
            doc=s.scalar(select(Document).where(Document.id==lookup.document_id).with_for_update())
            j=s.scalar(select(DocumentIngestionJob).where(DocumentIngestionJob.id==job_id).with_for_update().execution_options(populate_existing=True))
            if j.status!='queued':return
            j.status='processing';j.progress_percent=10;j.started_at=now();j.attempts+=1;j.lease_token=token;j.lease_until=now()+timedelta(seconds=self.LEASE_SECONDS)
            payload,filename,docid=j.source_payload,j.filename,str(j.document_id)
        stop=Event()
        def heartbeat():
            while not stop.wait(15):
                try:
                    with self._session_factory.begin() as s:
                        result=s.execute(update(DocumentIngestionJob).where(DocumentIngestionJob.id==job_id,DocumentIngestionJob.status=='processing',DocumentIngestionJob.lease_token==token,DocumentIngestionJob.lease_until>now()).values(lease_until=now()+timedelta(seconds=self.LEASE_SECONDS)))
                        if not result.rowcount:return
                except Exception:return
        beat=Thread(target=heartbeat,daemon=True);beat.start()
        try:
            if not payload or not payload.startswith(b'%PDF'):raise ValueError('文件不是有效的PDF。')
            pages=extract_pdf_bytes(payload,document_id=docid,document_name=filename)
            pages,preprocessing=prepare_pdf_pages(pages)
            if not pages:raise ValueError('PDF中没有可提取的文字，可能需要OCR。')
            chunks=[c for p in pages for c in chunk_document(p,chunk_size=self._chunk_size,overlap=self._chunk_overlap)]
            if not chunks:raise ValueError('文档没有生成可索引的文本块。')
            vectors=self._store.prepare_vectors(chunks)
            with self._session_factory.begin() as s:
                doc=s.scalar(select(Document).where(Document.id==UUID(docid)).with_for_update())
                j=s.scalar(select(DocumentIngestionJob).where(DocumentIngestionJob.id==job_id).with_for_update())
                if not doc or not j or j.status!='processing' or j.lease_token!=token or utc(j.lease_until)<=now():return
                if doc.content_revision!=j.base_revision:raise ValueError('资料版本已经变化，请刷新后重新处理。')
                if doc.status=='ready' or s.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id==doc.id)):capture(s,doc)
                page_rows=[dict(page_number=p.page_number,chapter=p.chapter,content=p.text) for p in pages]
                chunk_rows=[dict(page_number=c.page_number,chapter=c.chapter,position=i,content=c.text,metadata=c.metadata,embedding=v) for i,(c,v) in enumerate(zip(chunks,vectors,strict=True))]
                replace(s,doc,page_rows,chunk_rows)
                doc.content_revision+=1;doc.filename=filename;doc.external_model_allowed=False
                capture(s,doc,payload=payload,preprocessing=preprocessing,creator_id=j.creator_id)
                j.status='completed';j.progress_percent=100;j.page_count=len(pages);j.chunk_count=len(chunks);j.error_message=None;j.finished_at=now();j.lease_token=None;j.lease_until=None;j.source_payload=None
        except Exception as exc:
            with self._session_factory.begin() as s:
                doc=s.scalar(select(Document).where(Document.id==UUID(docid)).with_for_update())
                j=s.scalar(select(DocumentIngestionJob).where(DocumentIngestionJob.id==job_id).with_for_update())
                if not j or j.lease_token!=token or j.status!='processing':return
                j.status='failed';j.progress_percent=100;j.error_message=str(exc)[:1000];j.finished_at=now();j.lease_token=None;j.lease_until=None
                if doc and doc.status!='ready':doc.status='error';doc.error_message='资料处理失败，请查看任务并重试。'
        finally:stop.set();beat.join(timeout=1)

class DocumentTaskWorker:
    def __init__(self,service):self.service=service;self.stop_event=Event();self.thread=Thread(target=self.run,daemon=True)
    def start(self):self.thread.start()
    def stop(self):self.stop_event.set();self.thread.join(timeout=2)
    def run(self):
        while not self.stop_event.is_set():
            try:
                self.service.recover();job=self.service.pending()
                if job:self.service.process(job);continue
            except Exception:
                import logging
                logging.getLogger(__name__).warning('资料工作进程暂不可用，将稍后继续。')
            self.stop_event.wait(3)
