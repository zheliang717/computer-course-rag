from datetime import datetime, timedelta, timezone
from uuid import UUID
import pytest
from tests.test_account_lifecycle import setup
from app.assessment import AssessmentService
from app.models import Assignment, AssignmentSubmission, Course, CourseEnrollment, CourseSection, LateSubmissionRequest, QuestionBankItem, User


@pytest.fixture
def directory(setup):
    _,sessions,admin,teacher,course,*_=setup
    now=datetime.now(timezone.utc)
    with sessions.begin() as s:
        student=User(username='directory_student',display_name='同学',role='student',password_hash='unused',active=True,session_version=1)
        s.add(student);s.flush();sid=student.id
        s.add(CourseEnrollment(course_id=course,user_id=sid,status='active'))
        rows=[]
        for title,status,due in [('未来作业','published',now+timedelta(days=2)),('无限期','published',None),('逾期','published',now-timedelta(days=2)),('关闭','closed',None),('草稿','draft',None),('已交','published',None)]:
            a=Assignment(course_id=course,title=title,status=status,due_at=due);s.add(a);s.flush();rows.append(a.id)
        s.add(AssignmentSubmission(assignment_id=rows[-1],student_id=sid,answers={},status='submitted',score=0,max_score=10))
    return AssessmentService(sessions),sessions,UUID(teacher.id),sid,course,rows


def test_student_views_are_partitioned_before_pagination(directory):
    svc,_,t,s,c,rows=directory
    result=svc.list_assignments(user_id=s,role='student',page=1,page_size=1,task_view='todo',with_counts=True)
    assert result['total']==2 and len(result['items'])==1
    assert result['counts']=={'all':5,'todo':2,'late':2,'submitted':1}
    assert result['items'][0]['title']=='未来作业'
    assert svc.list_assignments(user_id=s,role='student',page=1,task_view='submitted')['items'][0]['submission_status']=='submitted'
    assert all(x['score'] is None for x in svc.list_assignments(user_id=s,role='student'))
    with pytest.raises(ValueError): svc.list_assignments(user_id=s,role='student',task_view='draft')


def test_approved_extension_and_teacher_grading(directory):
    svc,sessions,t,s,c,rows=directory
    with sessions.begin() as db: db.add(LateSubmissionRequest(assignment_id=rows[2],student_id=s,reason='补交安排',status='approved',approved_until=datetime.now(timezone.utc)+timedelta(days=1)))
    result=svc.list_assignments(user_id=s,role='student',page=1,task_view='todo',with_counts=True)
    assert result['counts']['todo']==3 and result['counts']['late']==1
    teacher=svc.list_assignments(user_id=t,role='teacher',page=1,task_view='grading',with_counts=True)
    assert teacher['total']==1 and teacher['items'][0]['ungraded_count']==1
    assert teacher['counts']['draft']==1 and teacher['counts']['ended']==2


def test_query_literal_scope_and_no_write(directory):
    svc,sessions,t,s,c,rows=directory
    with sessions.begin() as db:
        other=Course(title='他人课程',code='OUTSIDE',status='published');db.add(other);db.flush();oid=other.id
        db.add(Assignment(course_id=oid,title='他人作业',status='published'))
    assert svc.list_assignments(user_id=t,role='teacher',page=1,course_id=oid)['total']==0
    assert svc.list_assignments(user_id=s,role='student',page=1,keyword='%')['total']==0
    assert svc.list_assignments(user_id=s,role='student',page=1,keyword='未来')['total']==1
    assert svc.list_assignments(user_id=s,role='student',page=1,task_view='all')['total']==5


def test_question_section_difficulty_and_visibility(directory):
    svc,sessions,t,s,c,rows=directory
    with sessions.begin() as db:
        section=CourseSection(course_id=c,title='第一章',position=1);db.add(section);db.flush();sec=section.id
        for n in [2,4]: db.add(QuestionBankItem(course_id=c,section_id=sec,question_type='single_choice',stem=f'难度{n}',options=['A','B'],correct_answer='A',difficulty=n))
    result=svc.list_questions_page(user_id=s,role='student',course_id=c,section_id=sec,difficulty=4,keyword='',question_type=None,page=1,page_size=10)
    assert result['total']==1 and result['items'][0]['difficulty']==4 and result['items'][0]['correct_answer'] is None
    result=svc.list_questions_page(user_id=t,role='teacher',course_id=c,section_id=sec,difficulty=4,keyword='',question_type=None,page=1,page_size=10)
    assert result['items'][0]['correct_answer']=='A'
