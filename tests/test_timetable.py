from datetime import datetime, date, timezone, timedelta
from uuid import UUID
import pytest
from sqlalchemy import select
from tests.test_account_lifecycle import setup
from app.timetable import TimetableService, ScheduleConflict
from app.timetable_routes import Change, Calendar, Batch
from app.models import Course, CourseSession, TimetableRequest, TimetableEvent, User
from app.models import CourseEnrollment
from app.auth import principal_from_user


@pytest.fixture
def schedule(setup):
    _, sessions, admin, teacher, course, *_ = setup
    svc=TimetableService(sessions)
    with sessions.begin() as s: s.get(Course,course).semester='2026 秋季'
    row=svc.create(admin,course,dict(title='算法课',session_date=datetime(2026,11,2,2,tzinfo=timezone.utc),duration_minutes=90,location='A101'))
    return svc,sessions,admin,teacher,course,row


def move(row,**kw):
    return Change(expected_revision=row['revision'],reason='教学安排需要调整',session_date=datetime(2026,11,3,2,tzinfo=timezone.utc),**kw)


def test_request_approval_is_only_mutation(schedule):
    svc,sessions,a,t,c,row=schedule
    with pytest.raises(PermissionError): svc.change(t,UUID(row['id']),move(row))
    pending=svc.change(t,UUID(row['id']),move(row),request=True)
    assert svc.detail(t,UUID(row['id']))['session_date']==row['session_date']
    assert svc.requests(t,1,10)['total']==1
    svc.review(a,UUID(pending['id']),True,'已核对任课教师和教室')
    changed=svc.detail(t,UUID(row['id']))
    assert changed['session_date']!=row['session_date'] and changed['id']==row['id']
    assert not changed['completed'] and changed['revision']==2
    assert svc.events(t,1,5)['items'][0]['after'][0]['revision']==2
    with pytest.raises(ScheduleConflict): svc.review(a,UUID(pending['id']),True,'重复审批不允许执行')


def test_withdraw_reject_stale_and_cancel(schedule):
    svc,sessions,a,t,c,row=schedule
    pending=svc.change(t,UUID(row['id']),move(row),request=True)
    svc.withdraw(t,UUID(pending['id']))
    assert svc.detail(a,UUID(row['id']))==row
    pending=svc.change(t,UUID(row['id']),move(row),request=True)
    svc.change(a,UUID(row['id']),Change(kind='room',location='A202',reason='管理员调整上课教室',expected_revision=1))
    with pytest.raises(ScheduleConflict): svc.review(a,UUID(pending['id']),True,'已核对但原安排已变更')
    svc.review(a,UUID(pending['id']),False,'原安排已变化请重新申请')
    assert svc.detail(a,UUID(row['id']))['location']=='A202'
    changed=svc.change(a,UUID(row['id']),Change(kind='cancel',reason='校内活动本次暂停授课',expected_revision=2))
    assert changed['schedule_status']=='cancelled' and not changed['completed']
    with pytest.raises(ValueError): svc.complete(t,UUID(row['id']),True)
    assert svc.events(t,1,5)['total']==3


def test_conflict_approval_rolls_back_and_ownership(schedule):
    svc,sessions,a,t,c,row=schedule
    pending=svc.change(t,UUID(row['id']),move(row),request=True)
    svc.create(a,c,dict(title='另一课次',session_date=datetime(2026,11,3,2,tzinfo=timezone.utc),duration_minutes=90,location='B102'))
    with pytest.raises(ScheduleConflict): svc.review(a,UUID(pending['id']),True,'重新检查发现课程冲突')
    assert svc.detail(a,UUID(row['id']))==row
    assert svc.requests(a,1,10)['items'][0]['status']=='pending'
    with sessions.begin() as s: s.get(User,UUID(t.id)).active=False
    with pytest.raises(ScheduleConflict): svc.review(a,UUID(pending['id']),True,'教师账号状态发生变化')


def test_calendar_batch_preview_digest_and_holidays(schedule):
    svc,sessions,a,t,c,row=schedule
    calendar=Calendar(semester='2026 秋季',start_date=date(2026,11,2),end_date=date(2026,12,31),holidays=[date(2026,11,9)],expected_revision=0)
    with pytest.raises(PermissionError): svc.save_calendar(t,calendar)
    svc.save_calendar(a,calendar)
    data=Batch(course_id=c,title='周教学安排',start_week=1,end_week=3,weekdays=[1],start_time='15:00',duration_minutes=90,location='B202')
    preview=svc.batch(a,data)
    assert len(preview['items'])==2
    with pytest.raises(ScheduleConflict): svc.batch(a,data,commit=True)
    data.preview_digest=preview['digest'];data.confirmed=True
    assert svc.batch(a,data,commit=True)['count']==2
    with pytest.raises(ScheduleConflict): svc.batch(a,data,commit=True)
    assert len(svc.listing(t,date(2026,11,1),date(2026,11,30))['items'])==3
    with pytest.raises(ValueError): svc.listing(t,date(2026,11,1),date(2027,1,1))


def test_student_conflict_blocks_even_with_legacy_acknowledgement(schedule):
    svc,sessions,a,t,c,row=schedule
    with sessions.begin() as s:
        student=User(username='schedule_student',display_name='选课同学',role='student',active=True,password_hash='unused',session_version=1)
        s.add(student);s.flush();p=principal_from_user(student)
        s.add(CourseEnrollment(course_id=c,user_id=student.id,status='active'))
        other=Course(title='另一课程',code='OTHER',status='published',owner_id=UUID(a.id));s.add(other);s.flush();oc=other.id
        s.add(CourseEnrollment(course_id=oc,user_id=student.id,status='active'))
    with pytest.raises(ScheduleConflict) as exc:
        svc.create(a,oc,dict(title='学生重叠课',session_date=datetime.fromisoformat(row['session_date']),duration_minutes=90,location='C101'))
    assert all(x['blocking'] for x in exc.value.conflicts)
    with pytest.raises(ScheduleConflict):
        svc.create(a,oc,dict(title='不能勾选绕过',session_date=datetime.fromisoformat(row['session_date']),duration_minutes=90,location='C101'),ack=True)
    svc.create(a,oc,dict(title='重新设计排课',session_date=datetime.fromisoformat(row['session_date'])+timedelta(hours=2),duration_minutes=90,location='C101'),ack=True)
    assert len(svc.listing(p,date(2026,11,2),date(2026,11,3))['items'])==2
    with sessions.begin() as s: s.scalar(select(CourseEnrollment).where(CourseEnrollment.course_id==c)).status='removed'
    with pytest.raises(PermissionError): svc.detail(p,UUID(row['id']))
    assert len(svc.listing(p,date(2026,11,2),date(2026,11,3))['items'])==1


def test_admin_metadata_noop_and_inactive_principal(schedule):
    svc,sessions,a,t,c,row=schedule
    with pytest.raises(ValueError): svc.change(a,UUID(row['id']),Change(kind='room',location=row['location'],reason='未发生变化不能制造记录',expected_revision=1))
    with pytest.raises(PermissionError): svc.change(t,UUID(row['id']),move(row,title='教师不能改主题'),request=True)
    result=svc.change(a,UUID(row['id']),Change(kind='room',title='管理员维护课次主题',reason='按新课程大纲更新主题',expected_revision=1))
    assert result['title']=='管理员维护课次主题' and result['session_date']==row['session_date']
    with sessions.begin() as s: s.get(User,UUID(t.id)).session_version+=1
    with pytest.raises(PermissionError): svc.options(t)
