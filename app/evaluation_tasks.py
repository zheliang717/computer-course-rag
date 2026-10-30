"""Bounded offline evaluations with persisted claims and fenced result publication."""
import hashlib
import json
import logging
from datetime import datetime,timedelta,timezone
from pathlib import Path
from threading import Event,Thread
from uuid import UUID,uuid4
from sqlalchemy import select,func,text
from app.models import OperationalTask,EvaluationRun,Document,AuditLog
from app.pagination import sql_page
from app.retrieval_quality import quality_gate,gate_details
from app.evaluation_runner import evaluate,source_coverage

DATASETS={'dsa':('数据结构与算法 · 150题','questions-150-v2.json'),
    'osnet':('操作系统与网络 · 20题','os-net-zh-20.json'),
    'http':('HTTP · 10题','mdn-http-zh-10.json'),
    'memory':('地址空间 · 13题','learningos-address-space-zh-13.json')}
ROOT=Path(__file__).resolve().parent.parent/'materials'/'eval'
def now():return datetime.now(timezone.utc)
class LostClaim(Exception):pass

class EvaluationTasks:
    def __init__(self,sessions,retrieval):self.sessions=sessions;self.retrieval=retrieval
    @staticmethod
    def view(row):return {k:(str(v) if isinstance(v,UUID) else v) for k in ('id','request_id','actor_id','parameters','status','progress','attempt','result','error','created_at') if (v:=getattr(row,k,None)) is not None}
    def create(self,actor,request_id,dataset):
        if dataset not in DATASETS:raise ValueError('请选择已有评测题集。')
        params={'dataset':dataset}
        with self.sessions.begin() as s:
            s.execute(text('SELECT pg_advisory_xact_lock(672984532)'))
            row=s.scalar(select(OperationalTask).where(OperationalTask.request_id==request_id))
            if row:
                if row.actor_id!=UUID(actor.id) or row.parameters!=params:raise ValueError('请求编号已使用，请刷新后核对。')
                return self.view(row)
            if s.scalar(select(func.count()).select_from(OperationalTask).where(OperationalTask.status.in_(['queued','processing'])))>=3:raise ValueError('评测队列已满，请等待现有任务完成。')
            row=OperationalTask(actor_id=UUID(actor.id),request_id=request_id,kind='retrieval_evaluation',parameters=params)
            s.add(row);s.flush()
            s.add(AuditLog(actor_id=UUID(actor.id),actor_name=actor.display_name,action='start_evaluation',resource_type='operational_task',resource_id=str(row.id),detail=params))
            return self.view(row)
    def page(self,page,page_size):
        with self.sessions() as s:return sql_page(s,select(OperationalTask).where(OperationalTask.kind=='retrieval_evaluation').order_by(OperationalTask.created_at.desc(),OperationalTask.id.desc()),page=page,page_size=page_size,mapper=self.view)
    def get(self,task_id):
        with self.sessions() as s:
            row=s.get(OperationalTask,task_id);return self.view(row) if row and row.kind=='retrieval_evaluation' else None
    def cancel(self,task_id,actor):
        with self.sessions.begin() as s:
            row=s.scalar(select(OperationalTask).where(OperationalTask.id==task_id).with_for_update())
            if not row:raise ValueError('任务不存在。')
            if row.status in ('queued','processing'):
                row.status='cancelled';row.lease_token=None;row.lease_until=None
                s.add(AuditLog(actor_id=UUID(actor.id),actor_name=actor.display_name,action='cancel_evaluation',resource_type='operational_task',resource_id=str(row.id),detail={}))
            return self.view(row)
    def recover(self):
        with self.sessions.begin() as s:
            rows=s.scalars(select(OperationalTask).where(OperationalTask.kind=='retrieval_evaluation',OperationalTask.status=='processing',OperationalTask.lease_until<now()).with_for_update(skip_locked=True)).all()
            for row in rows:
                row.status='queued' if row.attempt<3 else 'failed';row.error='任务中断，已重新排队。' if row.attempt<3 else '连续中断，请重新发起评测。';row.lease_token=None;row.lease_until=None
    def _sources(self):
        with self.sessions() as s:
            rows=s.execute(select(Document.knowledge_base_id,Document.id,Document.filename,Document.content_revision).where(Document.status=='ready',Document.publication_status=='published').order_by(Document.id)).all()
            available={None:set()}
            for base,did,name,rev in rows:
                available.setdefault(str(base),set()).update((str(did),name));available[None].update((str(did),name))
            fingerprint=hashlib.sha256(json.dumps([(str(b),str(d),n,r) for b,d,n,r in rows],ensure_ascii=False).encode()).hexdigest()
            return available,fingerprint
    def process_one(self):
        with self.sessions.begin() as s:
            row=s.scalar(select(OperationalTask).where(OperationalTask.kind=='retrieval_evaluation',OperationalTask.status=='queued').order_by(OperationalTask.created_at,OperationalTask.id).with_for_update(skip_locked=True).limit(1))
            if not row:return False
            tid=row.id;claim=uuid4();row.lease_token=claim;row.lease_until=now()+timedelta(seconds=120);row.status='processing';row.attempt+=1;row.progress=1;row.error=None;params=row.parameters
        def checkpoint(index,total):
            with self.sessions.begin() as s:
                r=s.scalar(select(OperationalTask).where(OperationalTask.id==tid).with_for_update())
                if not r or r.status!='processing' or r.lease_token!=claim or not r.lease_until or r.lease_until<=now():raise LostClaim()
                r.progress=max(1,min(99,int(index/max(1,total)*100)));r.lease_until=now()+timedelta(seconds=120)
        try:
            active=self.retrieval() if callable(self.retrieval) else self.retrieval
            config={'top_k':getattr(active,'_top_k',None),'min_score':getattr(active,'_min_score',None)}
            from app.pgvector_store import PgVectorStore
            from app.rag import RetrievalService
            current_store=getattr(active,'_store',None)
            if isinstance(current_store,PgVectorStore):
                config.update(vector_weight=current_store._vector_weight,embedder=type(current_store._embedder).__name__)
                active=RetrievalService(PgVectorStore(self.sessions,current_store._embedder,vector_weight=config['vector_weight']),min_score=config['min_score'],top_k=config['top_k'])
            payload=(ROOT/DATASETS[params['dataset']][1]).read_bytes();dataset=json.loads(payload)
            available,fingerprint=self._sources();scope=dataset.get('knowledge_base_id')
            metrics,details=evaluate(active,dataset['cases'],keep_details=True,knowledge_base_id=scope,checkpoint=checkpoint)
            _,after=self._sources()
            if after!=fingerprint:raise ValueError('评测期间资料发生变化，请等待资料处理完成后重新评测。')
            coverage=source_coverage(dataset['cases'],available,scope)
            metrics.update(quality_gate=quality_gate(metrics,coverage),gate_details=gate_details(metrics,coverage),source_coverage=coverage,
                source_fingerprint=fingerprint,dataset_sha256=hashlib.sha256(payload).hexdigest(),retrieval_config=config)
            checkpoint(len(dataset['cases']),len(dataset['cases']))
            with self.sessions.begin() as s:
                r=s.scalar(select(OperationalTask).where(OperationalTask.id==tid).with_for_update())
                if r.status!='processing' or r.lease_token!=claim or r.lease_until<=now():raise LostClaim()
                run=EvaluationRun(name='检索评测 · '+DATASETS[params['dataset']][0],dataset_version=dataset['dataset_version'],case_count=len(dataset['cases']),metrics=metrics,details=details,created_by=str(r.actor_id));s.add(run);s.flush()
                r.status='completed';r.progress=100;r.result={'evaluation_id':str(run.id),'quality_gate':metrics['quality_gate']};r.lease_token=None;r.lease_until=None
        except LostClaim:pass
        except Exception as exc:
            logging.getLogger(__name__).exception('Offline evaluation failed')
            with self.sessions.begin() as s:
                r=s.scalar(select(OperationalTask).where(OperationalTask.id==tid).with_for_update())
                if r and r.status=='processing' and r.lease_token==claim:
                    r.status='failed';r.error=str(exc)[:300] if isinstance(exc,ValueError) else '评测失败，请检查资料与服务状态后重新发起。';r.lease_token=None;r.lease_until=None
        return True

class EvaluationWorker:
    def __init__(self,service):self.service=service;self.event=Event();self.thread=None
    def start(self):
        self.thread=Thread(target=self.run,daemon=True,name='offline-evaluations');self.thread.start()
    def run(self):
        while not self.event.is_set():
            try:
                self.service.recover()
                if self.service.process_one():continue
            except Exception:logging.getLogger(__name__).exception('Evaluation worker iteration failed')
            self.event.wait(3)
    def stop(self):self.event.set();self.thread and self.thread.join(timeout=5)
