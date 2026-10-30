from datetime import date, datetime, time, timezone, timedelta
from uuid import UUID
import pytest
from sqlalchemy import select
from tests.test_timetable import schedule
from tests.test_account_lifecycle import setup
from app.timetable import ScheduleConflict
from app.timetable_routes import Calendar, Change
from app.timetable_resources import ResourceInput, resource_state, resource_suggestions
from app.schedule_planning import SchedulePlanningService, CandidateInput, ReplanInput
from app.models import Course, CourseSession, TimetableCalendar


def resources(svc, admin, teacher, course, **kwargs):
    svc.save_calendar(admin,Calendar(semester='2026 秋季',start_date=date(2026,11,2),end_date=date(2026,12,31),expected_revision=0,rooms=['A101','B102']))
    data=ResourceInput(semester='2026 秋季',expected_revision=0,resource_mode='enforced',rooms=[
        {'code':'A-101','name':'第一教学楼101','aliases':['A101'],'capacity':40,'equipment':['投影']},
        {'code':'B-102','name':'第二教学楼102','aliases':['B102'],'capacity':20,'equipment':['计算机','投影']}],
        availability=[{'teacher_id':teacher.id,'slots':[{'weekday':1,'start':'10:00','end':'12:00'},{'weekday':2,'start':'08:00','end':'12:00'}]}],
        requirements=[{'course_id':course,'equipment':['计算机']}],**kwargs)
    return resource_state(svc,admin,'2026 秋季',data)


def test_capacity_equipment_availability_and_alias_enforced(schedule):
    svc,sessions,a,t,c,row=schedule
    resources(svc,a,t,c)
    planner=SchedulePlanningService(svc)
    findings=planner.audit(a,date(2026,11,2),date(2026,11,3),1,20)
    assert any('设备' in x['message'] for x in findings['items'])
    with pytest.raises(ScheduleConflict): svc.create(a,c,dict(title='缺设备',session_date=datetime(2026,11,3,2,tzinfo=timezone.utc),duration_minutes=90,location='A101'))
    with pytest.raises(ScheduleConflict): svc.create(a,c,dict(title='教师不可用',session_date=datetime(2026,11,4,2,tzinfo=timezone.utc),duration_minutes=90,location='B102'))
    result=svc.create(a,c,dict(title='有效教室',session_date=datetime(2026,11,3,2,tzinfo=timezone.utc),duration_minutes=90,location='B102'))
    assert result['location']=='第二教学楼102'
    with pytest.raises(ScheduleConflict): svc.create(a,c,dict(title='未知教室',session_date=datetime(2026,11,3,0,tzinfo=timezone.utc),duration_minutes=90,location='未登记'))
    with pytest.raises(PermissionError): resource_state(svc,t,'2026 秋季')


def test_candidates_are_not_writes_and_replan_requires_current_preview(schedule):
    svc,sessions,a,t,c,row=schedule
    resources(svc,a,t,c)
    planner=SchedulePlanningService(svc)
    window={'start_date':date(2026,11,2),'end_date':date(2026,11,3)}
    candidates=planner.candidates(t,UUID(row['id']),CandidateInput(**window))
    assert candidates['items'] and all(x['location']=='B-102' for x in candidates['items'])
    assert svc.detail(t,UUID(row['id']))['location']=='A101'
    data=ReplanInput(session_ids=[UUID(row['id'])],**window)
    preview=planner.replan(a,data)
    assert preview['ready'] and preview['proposed'][0]['location']=='B-102'
    with pytest.raises(ScheduleConflict): planner.replan(a,data,True)
    applied=planner.replan(a,data.model_copy(update={'signature':preview['signature'],'confirmed':True}),True)
    assert applied['updated_count']==1 and svc.detail(t,UUID(row['id']))['revision']==2
    with pytest.raises(ScheduleConflict): planner.replan(a,data.model_copy(update={'signature':preview['signature'],'confirmed':True}),True)


def test_no_feasible_greedy_plan_never_partially_writes(schedule):
    svc,sessions,a,t,c,row=schedule
    resources(svc,a,t,c)
    planner=SchedulePlanningService(svc)
    data=ReplanInput(session_ids=[UUID(row['id'])],start_date=date(2026,11,4),end_date=date(2026,11,4))
    preview=planner.replan(a,data)
    assert not preview['ready'] and preview['unresolved']
    with pytest.raises(ScheduleConflict): planner.replan(a,data.model_copy(update={'signature':preview['signature'],'confirmed':True}),True)
    assert svc.detail(t,UUID(row['id']))['revision']==1


def test_default_specs_need_no_invented_calendar_and_are_advisory(schedule):
    svc,sessions,a,t,c,row=schedule
    suggestion=resource_suggestions(svc,a,'2026 秋季')
    assert suggestion['resource_mode']=='advisory'
    assert suggestion['specification_source']=='editable_default'
    assert all(r['capacity'] in {30,40,60} for r in suggestion['rooms'])
    suggestion.pop('notice')
    state=resource_state(svc,a,'2026 秋季',ResourceInput(**suggestion,expected_revision=0))
    assert state['revision']==1
    with sessions() as s: assert s.scalar(select(TimetableCalendar)) is None
    # Resource uncertainty is advisory; real overlapping teaching time never is.
    result=svc.create(a,c,dict(title='未登记场地可提醒',session_date=datetime(2026,11,3,2,tzinfo=timezone.utc),duration_minutes=90,location='未来实验室'))
    findings=SchedulePlanningService(svc).audit(a,date(2026,11,3),date(2026,11,3),1,20)
    assert any(not x['blocking'] and '登记' in x['message'] for x in findings['items'])
    with pytest.raises(ScheduleConflict):
        svc.create(a,c,dict(title='时间仍冲突',session_date=datetime(2026,11,3,2,tzinfo=timezone.utc),duration_minutes=90,location='另一场地'))
    assert svc.detail(t,UUID(result['id']))['revision']==1


def test_duplicate_room_codes_rejected_even_with_different_names():
    with pytest.raises(ValueError):
        ResourceInput(semester='测试学期',expected_revision=0,rooms=[
            {'code':'A-1','name':'教室一','capacity':40,'equipment':[]},
            {'code':'A-1','name':'教室二','capacity':60,'equipment':[]}])


def test_room_identity_blocks_across_catalog_and_unconfigured_semesters(schedule):
    svc,sessions,a,t,c,row=schedule
    # One catalog also resolves raw legacy names in another semester.
    with sessions.begin() as s:
        other=Course(title='另一学期课程',code='OTHER-TERM',semester='2026 春季',owner_id=UUID(t.id),status='published')
        s.add(other);s.flush();other_id=other.id
    resources(svc,a,t,c)
    # Same room's canonical code and its legacy spelling must conflict even when
    # the other course has no resource catalog at all.
    with pytest.raises(ScheduleConflict) as exc:
        svc.create(a,other_id,dict(title='跨学期场地冲突',session_date=datetime.fromisoformat(row['session_date']),duration_minutes=90,location='A-101'))
    assert any('场地冲突' in x['message'] for x in exc.value.conflicts)
    with pytest.raises(ValueError):
        resource_state(svc,a,'2026 春季',ResourceInput(semester='2026 春季',expected_revision=0,rooms=[
            {'code':'A-101','name':'完全不同的楼宇','capacity':60,'equipment':[]}]))
    with pytest.raises(ValueError):
        resource_state(svc,a,'2026 春季',ResourceInput(semester='2026 春季',expected_revision=0,rooms=[
            {'code':'WRONG-ID','name':'第一教学楼101','capacity':60,'equipment':[]}]))
