from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID,uuid4
from types import SimpleNamespace
import pytest
import pymupdf
from sqlalchemy import select,func
from app.auth import Principal
from app.catalog import KnowledgeCatalog
from app.embedding import HashingEmbedder
from app.pgvector_store import PgVectorStore
from app.ingestion_jobs import DocumentIngestionService,now
from app.document_versions import DocumentVersionService
from app.models import Document,DocumentIngestionJob,DocumentVersion,KnowledgeBase,Chunk,User

def pdf(text):
    doc=pymupdf.open();p=doc.new_page();p.insert_text((40,60),text);payload=doc.tobytes();doc.close();return payload

@pytest.fixture
def setup(postgres_sessions):
    sessions=postgres_sessions
    with sessions.begin() as s:
        u=User(username='recovery_owner',display_name='Teacher',password_hash='x',role='teacher');s.add(u);s.flush()
        base=KnowledgeBase(name='Recovery',course='Recovery',created_by=u.id);s.add(base);s.flush();uid,bid=u.id,base.id
    catalog=KnowledgeCatalog(sessions);store=PgVectorStore(sessions,HashingEmbedder(512))
    service=DocumentIngestionService(sessions,catalog,store,chunk_size=200,chunk_overlap=30)
    def create(payload):return service.create(knowledge_base_id=bid,document_key=str(bid)+':book',filename='Book',content_type='application/pdf',payload=payload,creator_id=uid)
    return sessions,catalog,store,service,create,uid

def test_bad_reupload_and_embedding_failure_preserve_old_content_and_approval(setup):
    sessions,catalog,store,svc,create,uid=setup
    job=create(pdf('Original stack uses LIFO.'));svc.process(UUID(job['id']));did=UUID(job['document_id'])
    with sessions.begin() as s:s.get(Document,did).external_model_allowed=True
    with sessions() as s:before=[(c.id,c.content,list(c.embedding)) for c in s.scalars(select(Chunk))]
    broken=create(b'%PDF-broken');assert catalog.get_document(did)[0].status=='ready'
    svc.process(UUID(broken['id']));assert svc.get(UUID(broken['id']))['status']=='failed'
    assert catalog.get_document(did)[0].external_model_allowed
    store.prepare_vectors=lambda _: (_ for _ in ()).throw(RuntimeError('embedding unavailable'))
    failed=create(pdf('Updated candidate.'));svc.process(UUID(failed['id']))
    with sessions() as s:
        assert [(c.id,c.content,list(c.embedding)) for c in s.scalars(select(Chunk))]==before
        assert s.get(Document,did).content_revision==1

def test_orphaned_jobs_recovered_and_duplicate_claim_only_publishes_once(setup):
    sessions,_,_,svc,create,_=setup
    job=create(pdf('Recovered original.'));jid=UUID(job['id'])
    with sessions.begin() as s:
        j=s.get(DocumentIngestionJob,jid);j.status='processing';j.attempts=1;j.lease_token=uuid4();j.lease_until=now()-timedelta(seconds=1)
    assert svc.recover()==1
    with ThreadPoolExecutor(2) as pool:list(pool.map(svc.process,[jid,jid]))
    assert svc.get(jid)['status']=='completed'
    with sessions() as s:
        assert s.get(Document,UUID(job['document_id'])).content_revision==1
        assert s.scalar(select(func.count()).select_from(DocumentVersion))==1

@pytest.mark.parametrize('fault',['cancel','lost_lease'])
def test_cancel_or_lost_lease_blocks_late_publication(setup,fault):
    sessions,_,store,svc,create,uid=setup
    job=create(pdf('Must never publish.'));jid=UUID(job['id']);original=store.prepare_vectors
    def prepare(chunks):
        if fault=='cancel':svc.cancel(jid,actor_id=uid,actor_name='Teacher')
        else:
            with sessions.begin() as s:s.get(DocumentIngestionJob,jid).lease_until=now()-timedelta(seconds=1)
        return original(chunks)
    store.prepare_vectors=prepare;svc.process(jid)
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Chunk))==0
        assert s.scalar(select(func.count()).select_from(DocumentVersion))==0
    if fault=='cancel':assert svc.get(jid)['status']=='cancelled'

def test_versions_restore_with_revision_and_active_job_guards(setup):
    sessions,catalog,_,svc,create,uid=setup
    first=create(pdf('First content.'));svc.process(UUID(first['id']));did=UUID(first['document_id'])
    second=create(pdf('Second content.'));svc.process(UUID(second['id']))
    versions=DocumentVersionService(sessions);actor=Principal(id=str(uid),username='recovery_owner',display_name='Teacher',role='teacher')
    assert versions.list(did,1,6)['total']==2
    with pytest.raises(ValueError):versions.restore(did,1,1,actor)
    result=versions.restore(did,1,2,actor);assert result['current_revision']==3
    assert 'First content.' in catalog.get_document_content(did)[1][0]['content']
    assert not catalog.get_document(did)[0].external_model_allowed
    waiting=create(pdf('Third pending.'))
    with pytest.raises(ValueError):versions.restore(did,2,3,actor)
    svc.cancel(UUID(waiting['id']),actor_id=uid,actor_name='Teacher')
    versions.restore(did,2,3,actor)
    assert 'Second content.' in catalog.get_document_content(did)[1][0]['content']
