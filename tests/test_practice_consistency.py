from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4
import os
import pytest
from sqlalchemy import select, func
from tests.test_account_lifecycle import setup
from app.assessment import AssessmentService
from app.models import (User, CourseEnrollment, QuestionBankItem, Assignment, AssignmentQuestion, AssignmentSubmission,
                        PracticeAttempt, PracticeSubmissionReceipt, WrongQuestion)


@pytest.fixture
def practice(setup):
    _,sessions,admin,teacher,course,*_=setup
    with sessions.begin() as s:
        student=User(username='practice_student',display_name='练习同学',role='student',active=True,password_hash='unused',session_version=1)
        s.add(student);s.flush();sid=student.id
        s.add(CourseEnrollment(course_id=course,user_id=sid,status='active'))
        q=QuestionBankItem(course_id=course,stem='栈的特征是？',question_type='single_choice',options=['A. 后进先出','B. 先进先出'],correct_answer='A',difficulty=2)
        s.add(q);s.flush();qid=q.id
        a=Assignment(course_id=course,title='巩固作业',status='published');s.add(a);s.flush();aid=a.id
        s.add(AssignmentQuestion(assignment_id=aid,question_id=qid,position=1,points=10))
    return AssessmentService(sessions),sessions,sid,qid,aid


def test_assignment_mistake_resets_practice_streak(practice):
    svc,sessions,sid,qid,aid=practice
    svc.submit_practice_attempt(qid,student_id=sid,answer='B')
    svc.submit_practice_attempt(qid,student_id=sid,answer='A')
    assert svc.submit_practice_attempt(qid,student_id=sid,answer='A')['mastered']
    svc.submit(aid,student_id=sid,answers={str(qid):'B'})
    wrong=svc.list_wrong_questions(student_id=sid)[0]
    assert not wrong['mastered'] and wrong['correct_streak']==0 and wrong['wrong_count']==2
    first=svc.submit_practice_attempt(qid,student_id=sid,answer='A')
    assert first['correct_streak']==1 and not first['mastered']
    assert svc.submit_practice_attempt(qid,student_id=sid,answer='A')['mastered']


def test_retry_reuses_immutable_receipt_not_current_mastery(practice):
    svc,sessions,sid,qid,aid=practice
    svc.submit_practice_attempt(qid,student_id=sid,answer='B')
    request=uuid4()
    first=svc.submit_practice_attempt(qid,student_id=sid,answer='A',request_id=request)
    assert svc.submit_practice_attempt(qid,student_id=sid,answer='A',request_id=request)==first
    second=svc.submit_practice_attempt(qid,student_id=sid,answer='A',request_id=uuid4())
    assert second['mastered'] and second['attempt_id']!=first['attempt_id']
    assert svc.submit_practice_attempt(qid,student_id=sid,answer='A',request_id=request)==first
    with sessions() as s:
        assert s.scalar(select(func.count(PracticeAttempt.id)))==3
        assert s.scalar(select(func.count(PracticeSubmissionReceipt.request_id)))==2
        assert s.scalar(select(WrongQuestion)).correct_streak==2


def test_request_id_is_bound_to_payload_and_owner(practice):
    svc,sessions,sid,qid,aid=practice
    request=uuid4()
    svc.submit_practice_attempt(qid,student_id=sid,answer='B',request_id=request)
    with pytest.raises(ValueError): svc.submit_practice_attempt(qid,student_id=sid,answer='A',request_id=request)
    with sessions.begin() as s:
        other=User(username='other_student',display_name='另一同学',role='student',active=True,password_hash='unused',session_version=1)
        s.add(other);s.flush();oid=other.id
        course=s.get(QuestionBankItem,qid).course_id
        s.add(CourseEnrollment(course_id=course,user_id=oid,status='active'))
    result=svc.submit_practice_attempt(qid,student_id=oid,answer='A',request_id=request)
    assert result['is_correct'] is True
    with sessions() as s: assert s.scalar(select(func.count(PracticeAttempt.id)))==2


def test_replay_rechecks_current_access(practice):
    svc,sessions,sid,qid,aid=practice
    request=uuid4();svc.submit_practice_attempt(qid,student_id=sid,answer='B',request_id=request)
    with sessions.begin() as s: s.scalar(select(CourseEnrollment).where(CourseEnrollment.user_id==sid)).status='inactive'
    with pytest.raises(LookupError): svc.submit_practice_attempt(qid,student_id=sid,answer='B',request_id=request)
    with sessions.begin() as s: s.get(User,sid).active=False
    with pytest.raises(LookupError): svc.submit_practice_attempt(qid,student_id=sid,answer='B')


def test_archive_filters_and_manual_endpoint_cannot_mark_progress(practice):
    svc,sessions,sid,qid,aid=practice
    svc.submit_practice_attempt(qid,student_id=sid,answer='B')
    wid=UUID(svc.list_wrong_questions(student_id=sid)[0]['id'])
    with pytest.raises(ValueError): svc.mark_mastered(wid,student_id=sid)
    assert svc.list_wrong_questions(student_id=sid,page=1,page_size=1,mastery='pending')['total']==1
    svc.submit_practice_attempt(qid,student_id=sid,answer='A')
    svc.submit_practice_attempt(qid,student_id=sid,answer='A')
    assert svc.list_wrong_questions(student_id=sid,page=1,mastery='pending')['total']==0
    assert svc.list_wrong_questions(student_id=sid,page=1,mastery='mastered',keyword='栈')['total']==1
    assert svc.list_wrong_questions(student_id=sid,page=1,mastery='all')['total']==1
    assert svc.mark_mastered(wid,student_id=sid)


def test_subjective_practice_does_not_auto_mark_mastery(practice):
    svc,sessions,sid,qid,aid=practice
    with sessions.begin() as s:
        q=QuestionBankItem(course_id=s.get(QuestionBankItem,qid).course_id,stem='说明栈的应用',question_type='short_answer',options=[],correct_answer='参考',difficulty=2)
        s.add(q);s.flush();qid=q.id
        s.add(WrongQuestion(student_id=sid,question_id=qid,wrong_count=1,correct_streak=0,mastered=False))
    result=svc.submit_practice_attempt(qid,student_id=sid,answer='我的说明',request_id=uuid4())
    assert result['needs_review'] and result['is_correct'] is None and not result['mastered']


@pytest.mark.skipif(not os.environ.get('ACCOUNT_TEST_DATABASE_URL'),reason='PostgreSQL row-lock acceptance only')
def test_concurrent_same_request_counts_once(practice):
    svc,sessions,sid,qid,aid=practice
    svc.submit_practice_attempt(qid,student_id=sid,answer='B')
    request=uuid4()
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:svc.submit_practice_attempt(qid,student_id=sid,answer='A',request_id=request),range(2)))
    assert results[0]==results[1] and results[0]['correct_streak']==1
    with sessions() as s: assert s.scalar(select(func.count(PracticeAttempt.id)))==2


@pytest.mark.skipif(not os.environ.get('ACCOUNT_TEST_DATABASE_URL'),reason='PostgreSQL row-lock acceptance only')
def test_concurrent_assignment_submission_counts_one_mistake(practice):
    svc,sessions,sid,qid,aid=practice
    def submit(_):
        try: svc.submit(aid,student_id=sid,answers={str(qid):'B'}); return 'saved'
        except ValueError: return 'already-submitted'
    with ThreadPoolExecutor(2) as pool: results=sorted(pool.map(submit,range(2)))
    assert results==['already-submitted','saved']
    with sessions() as s:
        assert s.scalar(select(func.count(AssignmentSubmission.id)))==1
        assert s.scalar(select(WrongQuestion)).wrong_count==1
