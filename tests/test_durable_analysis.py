"""Real PostgreSQL jobs/receipts, deterministic fake provider; no cloud calls."""
import json
from uuid import UUID, uuid4
from types import SimpleNamespace
import pytest
from sqlalchemy import select, func
from app import main
from app.auth import principal_from_user
from app.assistant_tasks import AssistantTaskService
from app.assignment_reviews import AssignmentReviewService
from app.student_answer_analysis import StudentAnswerAnalysisService
from app.course_cohort_analysis import CourseCohortAnalysisService
from app.model_usage import ModelUsageService
from app.models import (User, Course, CourseEnrollment, QuestionBankItem, Assignment,
    AssignmentQuestion, AssignmentSubmission, SubmissionReview, ModelQuota, ModelUsageLog, TeachingDraft)


@pytest.fixture
def analysis_jobs(postgres_sessions, monkeypatch):
    sessions=postgres_sessions
    with sessions.begin() as s:
        teacher=User(username='job_teacher',display_name='测试教师',role='teacher',password_hash='test',active=True,session_version=1)
        student=User(username='job_student',display_name='测试学生',role='student',password_hash='test',active=True,session_version=1)
        s.add_all([teacher,student]);s.flush()
        course=Course(title='测试数据结构',code='TEST-JOBS',owner_id=teacher.id,status='published')
        s.add(course);s.flush()
        s.add(CourseEnrollment(course_id=course.id,user_id=student.id,status='active'))
        q=QuestionBankItem(course_id=course.id,question_type='true_false',stem='栈是后进先出吗？',options=['正确','错误'],correct_answer='正确',explanation='栈后进先出',knowledge_point='栈')
        a=Assignment(course_id=course.id,creator_id=teacher.id,title='测试栈作业',status='published')
        s.add_all([q,a]);s.flush()
        s.add(AssignmentQuestion(assignment_id=a.id,question_id=q.id,points=10,position=1))
        sub=AssignmentSubmission(assignment_id=a.id,student_id=student.id,answers={str(q.id):'错误'},score=0,max_score=10,status='graded')
        s.add(sub);s.flush()
        s.add(SubmissionReview(submission_id=sub.id,teacher_id=teacher.id,score=0,feedback='再核对栈的顺序'))
        s.add(ModelQuota(role='teacher',daily_limit=50))
        principal=principal_from_user(teacher)
        identifiers={'assignment_review':a.id,'student_analysis':sub.id,'cohort_analysis':course.id}
        cid,qid=course.id,q.id
    jobs=AssistantTaskService(sessions)
    monkeypatch.setattr(main,'assignment_reviews',AssignmentReviewService(sessions))
    monkeypatch.setattr(main,'student_answer_analysis',StudentAnswerAnalysisService(sessions))
    monkeypatch.setattr(main,'course_cohort_analysis',CourseCohortAnalysisService(sessions))
    monkeypatch.setattr(main,'model_usage',ModelUsageService(sessions))
    monkeypatch.setattr(main,'settings',main.settings.model_copy(update={'llm_provider':'compatible','llm_model':'isolated-fake'}))
    return sessions,jobs,principal,cid,qid,identifiers


@pytest.mark.parametrize('kind',['assignment_review','student_analysis','cohort_analysis'])
@pytest.mark.parametrize('cancel_during_generation',[False,True])
def test_analysis_result_and_usage_commit_with_job_fence(analysis_jobs,monkeypatch,kind,cancel_during_generation):
    sessions,jobs,teacher,cid,qid,targets=analysis_jobs
    payload={'course_id':str(cid),'target_id':str(targets[kind]),'confirm_external_analysis':True,'include_student_answers':True,'local_only':False}
    request_id=uuid4()
    item=jobs.create(teacher,request_id,payload,kind)
    assert jobs.create(teacher,request_id,payload,kind)['id']==item['id']
    task_id,attempt,principal,claimed=jobs.claim()
    def generate(*args,**kwargs):
        if cancel_during_generation: jobs.action(teacher,task_id,'cancel')
        if kind=='assignment_review': return '## 作业讲评草稿\n\n请结合本题学生作答核对后进先出概念，不自动修改成绩。'
        if kind=='student_analysis': return json.dumps({'summary':'本题需要复习栈概念','question_reviews':[{'question_id':str(qid),'observation':'已提交答案与本题参考答案不一致','next_step':'用两个元素模拟入栈与出栈'}],'teaching_suggestions':['安排简短的出栈演示'],'feedback_draft':'再用实例核对后进先出。'})
        return json.dumps({'summary':'本次作业需要跟进','strengths':[],'concerns':['样本只有一人，不宜推断全班趋势'],'teaching_actions':['核对栈的概念并安排再练'],'student_suggestions':[]})
    monkeypatch.setattr(main,'generator',SimpleNamespace(generate=generate))
    if cancel_during_generation:
        with pytest.raises(Exception): main._execute_teacher_task(claimed,principal,(jobs,task_id,attempt,principal))
    else:
        main._execute_teacher_task(claimed,principal,(jobs,task_id,attempt,principal))
    result=jobs.get(teacher,task_id)
    with sessions() as s:
        logs=list(s.scalars(select(ModelUsageLog)))
        drafts=list(s.scalars(select(TeachingDraft)))
        assert len(logs)==1 and logs[0].error_type!='pending'
        assert s.scalar(select(AssignmentSubmission.score))==0
        assert s.scalar(select(SubmissionReview.score))==0
        if cancel_during_generation:
            assert result['status']=='cancelled' and not drafts and not logs[0].successful
        else:
            assert result['status']=='completed' and len(drafts)==1 and logs[0].successful
            assert result['result']['draft_id']==str(drafts[0].id)
            assert drafts[0].status=='draft'


def test_analysis_target_cannot_be_mislabeled_as_another_course(analysis_jobs):
    sessions,jobs,teacher,cid,_,targets=analysis_jobs
    with pytest.raises(ValueError):
        jobs.create(teacher,uuid4(),{'course_id':str(cid),'target_id':str(uuid4())},'assignment_review')


def test_cancel_after_model_reservation_cannot_refund_and_bypass_task_quota(analysis_jobs):
    sessions,jobs,teacher,cid,_,_=analysis_jobs
    with sessions.begin() as s:s.get(ModelQuota,'teacher').daily_limit=1
    body={'course_id':str(cid),'draft_type':'lesson_plan'}
    created=jobs.create(teacher,uuid4(),body)
    identifier,attempt,principal,_=jobs.claim()
    jobs.reserve_model(principal,identifier,attempt,feature='teacher_task',provider='compatible',model='fake')
    jobs.action(teacher,UUID(created['id']),'cancel')
    with sessions() as s:
        assert s.scalar(select(ModelUsageLog)).error_type=='task_cancelled'
    jobs.create(teacher,uuid4(),body)
    identifier,attempt,principal,_=jobs.claim()
    with pytest.raises(PermissionError,match='额度已用完'):
        jobs.reserve_model(principal,identifier,attempt,feature='teacher_task',provider='compatible',model='fake')
