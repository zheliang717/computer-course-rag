from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4,UUID
import pytest
from sqlalchemy import select,func
from app.models import User,OperationalTask,EvaluationRun
from app.auth import Principal
from app.evaluation_tasks import EvaluationTasks,now
from app.operations_routes import csv_response

@pytest.fixture
def setup(postgres_sessions):
    with postgres_sessions.begin() as s:
        u=User(username='evaladmin',display_name='Admin',role='admin',password_hash='x');s.add(u);s.flush();uid=u.id
    actor=Principal(str(uid),'evaladmin','Admin','admin')
    service=EvaluationTasks(postgres_sessions,SimpleNamespace(retrieve=lambda *a:SimpleNamespace(hits=[],accepted=False)))
    return postgres_sessions,actor,service

def test_idempotency_queue_recovery_and_truthful_failed_gate(setup):
    sessions,actor,svc=setup;rid=uuid4();a=svc.create(actor,rid,'http')
    assert svc.create(actor,rid,'http')['id']==a['id']
    with pytest.raises(ValueError):svc.create(actor,rid,'dsa')
    with sessions.begin() as s:
        row=s.get(OperationalTask,UUID(a['id']));row.status='processing';row.attempt=1;row.lease_until=now()-timedelta(seconds=1)
    svc.recover();assert svc.get(UUID(a['id']))['status']=='queued'
    assert svc.process_one();result=svc.get(UUID(a['id']));assert result['status']=='completed'
    with sessions() as s:
        run=s.get(EvaluationRun,UUID(result['result']['evaluation_id']));assert not run.metrics['quality_gate'];assert run.metrics['gate_details']['checks']['citation_accuracy'] is False
        assert s.scalar(select(func.count()).select_from(EvaluationRun))==1
    assert not svc.process_one()

def test_cancel_during_evaluation_fences_result(setup):
    sessions,actor,svc=setup;a=svc.create(actor,uuid4(),'http')
    def retrieve(*args):svc.cancel(UUID(a['id']),actor);return SimpleNamespace(hits=[],accepted=False)
    svc.retrieval.retrieve=retrieve
    assert svc.process_one();assert svc.get(UUID(a['id']))['status']=='cancelled'
    with sessions() as s:assert s.scalar(select(func.count()).select_from(EvaluationRun))==0

def test_csv_protects_formulas_and_rejects_silent_truncation():
    from fastapi import HTTPException
    r=csv_response([('v','内容')],[{'v':'=1+1'},{'v':'正常中文'}],'test')
    assert r.body.startswith(b'\xef\xbb\xbf');assert "'=1+1" in r.body.decode('utf-8')
    with pytest.raises(HTTPException):csv_response([('v','内容')],[{}]*10001,'large')
