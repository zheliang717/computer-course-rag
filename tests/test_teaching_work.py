from copy import deepcopy
from datetime import date, datetime, timezone
import json
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from tests.test_account_lifecycle import setup
from tests.test_timetable import schedule
from tests.test_schedule_planning import resources
from app.accounts import AccountService
from app.assistant_tasks import AssistantTaskService, TaskStopped
from app.assistant_schedule import AssistantSchedule
from app.auth import principal_from_user
from app.course_editor import CourseEditorService
from app.course_editor_routes import DraftInput
from app.material_questions import extract_questions
from app.models import (TeacherResource, TeachingWorkResult, TeachingDraft, QuestionBankItem, QuestionSource,
    CourseSession, CourseSection, CourseEnrollment, TimetableRequest, CourseAnnouncement, User, CourseContentState)
from app.teaching_drafts import TeachingDraftService
from app.teaching_resources import TeachingResources
from app.teaching_work import TeachingWorkService
from app.teaching_work_schemas import (MaterialTask, CourseTask, ScheduleTask, AdoptQuestions, AdoptCourse, AdoptSchedule)
from app.timetable import TimetableService, ScheduleConflict
from app.timetable_routes import Review


def pdf():
    import pymupdf
    doc=pymupdf.open(); page=doc.new_page()
    page.insert_text((40,40),'1. What is a stack?\nAnswer: LIFO\n2. Explain binary search.')
    value=doc.tobytes();doc.close();return value


def seed_quotas(sessions):
    from app.models import ModelQuota
    with sessions.begin() as s:
        for role in ('teacher','admin'):
            if not s.get(ModelQuota,role): s.add(ModelQuota(role=role,daily_limit=1000))


def work(sessions, actor, kind, payload, output=None):
    seed_quotas(sessions)
    tasks=AssistantTaskService(sessions)
    task=tasks.create(actor,uuid4(),payload,kind)
    task_id,attempt,principal,claimed=tasks.claim()
    service=TeachingWorkService(sessions,AssistantSchedule(TimetableService(sessions)))
    result=service.execute(principal,kind,claimed,(tasks,task_id,attempt,principal),
        lambda _:json.dumps(output,ensure_ascii=False),provider='mock',model='deterministic-test-model')
    assert tasks.get(actor,UUID(task['id']))['result']['workflow_id']==result['id']
    return service,result


def test_exact_cross_page_extraction_and_missing_answers():
    pages=[dict(page_number=2,content='1. 单选题：以下哪项正确？\nA. 栈是后进先出\n'),
        dict(page_number=3,content='B. 栈是先进先出\n答案：A\n解析：栈采用后进先出。\n2. 简答题：说明二分查找的条件。')]
    result=extract_questions(pages,dict(resource_id=str(uuid4()),title='习题选读'))
    assert len(result)==2 and result[0]['correct_answer']=='A' and len(result[0]['options'])==2
    assert [x['page_number'] for x in result[0]['source']['spans']]==[2,3]
    for candidate in result:
        for span in candidate['source']['spans']:
            original=next(x['content'] for x in pages if x['page_number']==span['page_number'])
            assert original[span['start_offset']:span['end_offset']]==span['quote']
    assert result[1]['correct_answer']=='' and result[1]['needs_answer']
    assert extract_questions([dict(page_number=1,content='没有题号的课程说明')],{})==[]
    with pytest.raises(ValueError): extract_questions(pages,{},excerpt='不在原文中的伪造问题')
    selected=extract_questions(pages,{},excerpt='说明二分查找的条件。')
    assert selected[0]['source']['origin']=='teacher_excerpt'


def test_teacher_resources_private_scoped_versioned_and_not_indexed(setup):
    _,sessions,admin,teacher,course,*_=setup
    resource=TeachingResources(sessions)
    row=resource.create(teacher,course,'课程习题.pdf',pdf(),identifier=uuid4())
    assert row['title']=='课程习题' and row['page_count']==1
    from app.teaching_work_schemas import ResourceEdit
    changed=resource.edit(teacher,course,UUID(row['id']),ResourceEdit(revision=1,title='课程题目选读',archived=True))
    assert changed['status']=='archived'
    with pytest.raises(ValueError): resource.edit(admin,course,UUID(row['id']),ResourceEdit(revision=1,title='覆盖旧版本'))
    with sessions.begin() as s:
        student=User(username='private_student',display_name='学生',role='student',password_hash='unused',active=True,session_version=1)
        s.add(student);s.flush();p=principal_from_user(student)
    with pytest.raises(PermissionError): resource.get(p,course,UUID(row['id']))
    from app.models import Document,Chunk
    with sessions() as s:
        assert not s.scalar(select(Document.id)) and not s.scalar(select(Chunk.id))
    with pytest.raises(ValueError): resource.create(teacher,course,'假文件',b'not pdf')


def test_selected_questions_remain_drafts_until_review_and_keep_provenance(setup):
    _,sessions,admin,teacher,course,*_=setup
    resource=TeachingResources(sessions).create(teacher,course,'课程练习',pdf())
    payload=MaterialTask(course_id=course,resource_id=resource['id']).model_dump(mode='json')
    service,result=work(sessions,teacher,'material_extract',payload)
    assert result['content']['candidates']
    selected={**result['content']['candidates'][0], 'correct_answer':'后进先出', 'explanation':'栈遵循后进先出规则。'}
    data=AdoptQuestions(revision=1,confirmed=True,questions=[selected])
    draft=service.adopt_questions(teacher,UUID(result['id']),data)
    assert service.adopt_questions(teacher,UUID(result['id']),data)==draft
    with sessions() as s: assert not s.scalar(select(QuestionBankItem.id))
    drafts=TeachingDraftService(sessions)
    drafts.update(UUID(draft['draft_id']),actor_id=UUID(teacher.id),role='teacher',data={'status':'confirmed'})
    _,ids=drafts.publish_questions(UUID(draft['draft_id']),actor_id=UUID(teacher.id),role='teacher')
    provenance=service.question_source(teacher,UUID(ids[0]))
    assert provenance['title']=='课程练习' and provenance['spans'][0]['page_number']==1
    assert provenance['teacher_confirmed'] and provenance['original_text']
    with pytest.raises(ValueError): drafts.publish_questions(UUID(draft['draft_id']),actor_id=UUID(teacher.id),role='teacher')


def test_missing_answer_can_be_saved_but_cannot_enter_question_bank(setup):
    _,sessions,_,teacher,course,*_=setup
    resource=TeachingResources(sessions).create(teacher,course,'课程练习',pdf())
    service,result=work(sessions,teacher,'material_extract',MaterialTask(course_id=course,resource_id=resource['id']).model_dump(mode='json'))
    candidate=result['content']['candidates'][-1]
    draft=service.adopt_questions(teacher,UUID(result['id']),AdoptQuestions(revision=1,confirmed=True,questions=[candidate]))
    drafts=TeachingDraftService(sessions);drafts.update(UUID(draft['draft_id']),actor_id=UUID(teacher.id),role='teacher',data={'status':'confirmed'})
    with pytest.raises(ValueError): drafts.publish_questions(UUID(draft['draft_id']),actor_id=UUID(teacher.id),role='teacher')
    with sessions() as s: assert not s.scalar(select(QuestionBankItem.id))


SUGGESTION=dict(description='课程介绍建议',learning_objectives='- 理解栈',assessment='考核建议，需教师核对',
    sections=[dict(title='栈与队列',description='理解基本操作',knowledge_points=['后进先出'])])


def test_course_suggestion_selective_adoption_only_updates_draft(setup):
    _,sessions,_,teacher,course,*_=setup
    service,result=work(sessions,teacher,'course_content',CourseTask(course_id=course,request='完善教学大纲').model_dump(mode='json'),SUGGESTION)
    data=AdoptCourse(revision=1,confirmed=True,fields=['learning_objectives','sections'],suggestion=SUGGESTION)
    service.adopt_course(teacher,UUID(result['id']),data)
    state=CourseEditorService(sessions).get(teacher,course)
    assert state['has_draft'] and state['content']['learning_objectives']=='- 理解栈'
    assert state['content']['description']=='' and state['live']['sections']==[]
    assert state['content']['sections'][0]['title']=='栈与队列'
    assert state['content']['knowledge_points'][0]['name']=='后进先出'
    with pytest.raises(ValueError): service.adopt_course(teacher,UUID(result['id']),data)


def test_course_suggestion_rejects_newer_editor_and_revoked_source(setup):
    _,sessions,_,teacher,course,*_=setup
    service,result=work(sessions,teacher,'course_content',CourseTask(course_id=course,request='完善教学大纲').model_dump(mode='json'),SUGGESTION)
    editor=CourseEditorService(sessions);state=editor.get(teacher,course)
    editor.save(teacher,course,DraftInput(revision=0,base_signature=state['base_signature'],content={**state['content'],'description':'教师的新修改'}))
    with pytest.raises(ValueError,match='草稿已变化'): service.adopt_course(teacher,UUID(result['id']),AdoptCourse(revision=1,confirmed=True,fields=['description'],suggestion=SUGGESTION))
    resource=TeachingResources(sessions).create(teacher,course,'教师题目',pdf())
    with sessions.begin() as s:
        actor=AccountService.actor(s,teacher)
        with pytest.raises(ValueError): TeachingResources.source(s,actor,course,CourseTask(course_id=course,request='完善课程',resource_id=resource['id'],allow_external=True),online=True)


def test_section_archive_preserves_history_and_can_restore(setup):
    _,sessions,_,teacher,course,*_=setup
    with sessions.begin() as s:
        row=CourseSection(course_id=course,title='历史章节',position=1);s.add(row);s.flush();sid=row.id
        s.add(CourseSession(course_id=course,section_id=sid,title='历史课次',session_date=datetime(2026,1,1,tzinfo=timezone.utc),completed=True))
    editor=CourseEditorService(sessions);state=editor.get(teacher,course)
    state['content']['sections'][0]['archived']=True
    saved=editor.save(teacher,course,DraftInput(revision=0,base_signature=state['base_signature'],content=state['content']))
    editor.publish(teacher,course,saved['revision'],True)
    from app.learning import LearningService
    assert LearningService(sessions).get_course(course,user_id=UUID(teacher.id),role='teacher').sections==[]
    state=editor.get(teacher,course);state['content']['sections'][0]['archived']=False
    saved=editor.save(teacher,course,DraftInput(revision=state['revision'],base_signature=state['base_signature'],content=state['content']))
    editor.publish(teacher,course,saved['revision'],True)
    with sessions() as s: assert s.scalar(select(CourseSession)).section_id==sid


def schedule_payload(course,row=None):
    return ScheduleTask(course_id=course,request='优先机房，安排在周二上午，避开已有课',start_date=date(2026,11,2),end_date=date(2026,11,3),
        session_ids=[row['id']] if row else [],count=2,day_start='08:00',day_end='12:00',weekdays=[1,2]).model_dump(mode='json')


CONDITIONS=dict(day_start='08:00',day_end='12:00',weekdays=[2],rooms=['B-102'],explanation='选择有计算机的机房，由程序验证冲突。')


def test_ai_schedule_admin_new_lessons_preview_confirm_and_notifications(schedule):
    tt,sessions,a,t,c,row=schedule;resources(tt,a,t,c)
    before=None
    with sessions() as s: before=s.scalar(select(func.count()).select_from(CourseSession))
    service,result=work(sessions,a,'schedule_plan',schedule_payload(c),CONDITIONS)
    assert result['content']['choices'] and len(result['content']['choices'][0]['proposed'])==2
    with sessions() as s: assert s.scalar(select(func.count()).select_from(CourseSession))==before
    with pytest.raises(ValueError): service.adopt_schedule(a,UUID(result['id']),AdoptSchedule(revision=1,option=0,reason='确认测试安排'))
    service.adopt_schedule(a,UUID(result['id']),AdoptSchedule(revision=1,option=0,reason='确认测试安排',confirmed=True))
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(CourseSession))==before+2
        assert s.scalar(select(CourseAnnouncement).where(CourseAnnouncement.title=='课程安排更新'))
    with pytest.raises(ValueError): service.adopt_schedule(a,UUID(result['id']),AdoptSchedule(revision=1,option=0,reason='重复确认安排',confirmed=True))


def test_ai_schedule_teacher_only_requests_and_rechecks_conflicts(schedule):
    tt,sessions,a,t,c,row=schedule;resources(tt,a,t,c)
    service,result=work(sessions,t,'schedule_plan',schedule_payload(c,row),CONDITIONS)
    adopted=service.adopt_schedule(t,UUID(result['id']),AdoptSchedule(revision=1,option=0,reason='需要调整上课日期',confirmed=True))
    with sessions() as s: assert tt.snapshot(s.get(CourseSession,UUID(row['id'])))['session_date']==row['session_date']
    request=tt.review(a,UUID(adopted['request_id']),True,'管理员核对后通过')
    assert request['status']=='approved'
    with sessions() as s: assert tt.snapshot(s.get(CourseSession,UUID(row['id'])))['session_date']!=row['session_date']


def test_ai_schedule_rejects_stale_roster_and_invented_rooms(schedule):
    tt,sessions,a,t,c,row=schedule;resources(tt,a,t,c)
    service,result=work(sessions,a,'schedule_plan',schedule_payload(c),CONDITIONS)
    with sessions.begin() as s:
        student=User(username='new_roster',display_name='新成员',role='student',password_hash='unused',active=True,session_version=1)
        s.add(student);s.flush();s.add(CourseEnrollment(course_id=c,user_id=student.id,status='active'))
    with pytest.raises(ScheduleConflict): service.adopt_schedule(a,UUID(result['id']),AdoptSchedule(revision=1,option=0,reason='名单变化不应通过',confirmed=True))
    with pytest.raises(ValueError): work(sessions,a,'schedule_plan',schedule_payload(c),{**CONDITIONS,'rooms':['不存在的教室']})


def test_cancelled_workflow_does_not_save_late_model_output(setup):
    _,sessions,_,teacher,course,*_=setup
    seed_quotas(sessions)
    tasks=AssistantTaskService(sessions);task=tasks.create(teacher,uuid4(),CourseTask(course_id=course,request='完善课程内容').model_dump(mode='json'),'course_content')
    tid,attempt,principal,payload=tasks.claim()
    def generate(_):
        tasks.action(teacher,tid,'cancel')
        return json.dumps(SUGGESTION)
    service=TeachingWorkService(sessions,AssistantSchedule(TimetableService(sessions)))
    with pytest.raises(TaskStopped): service.execute(principal,'course_content',payload,(tasks,tid,attempt,principal),generate,provider='mock',model='test')
    with sessions() as s: assert not s.scalar(select(TeachingWorkResult.id))


def test_schedule_preferences_can_be_rechecked_without_another_model_call(schedule):
    from app.teaching_work_schemas import ReviseSchedule
    tt,sessions,a,t,c,row=schedule;resources(tt,a,t,c)
    service,result=work(sessions,a,'schedule_plan',schedule_payload(c),CONDITIONS)
    identifier=UUID(result['id'])
    with sessions.begin() as s:
        student=User(username='late_member',display_name='新增成员',role='student',password_hash='unused',active=True,session_version=1)
        s.add(student);s.flush();s.add(CourseEnrollment(course_id=c,user_id=student.id,status='active'))
    refreshed=service.revise_schedule(a,identifier,ReviseSchedule(revision=1,conditions={**CONDITIONS,'day_start':'09:00'}))
    assert refreshed['revision']==2 and refreshed['content']['conditions']['day_start']=='09:00'
    assert refreshed['content']['student_count']==1 and refreshed['content']['choices']
    with pytest.raises(ValueError): service.adopt_schedule(a,identifier,AdoptSchedule(revision=1,option=0,reason='不能采纳旧版预览',confirmed=True))
    with pytest.raises(ValueError): service.revise_schedule(a,identifier,ReviseSchedule(revision=2,conditions={**CONDITIONS,'day_start':'07:00'}))
    assert service.get(a,identifier)['revision']==2
    service.adopt_schedule(a,identifier,AdoptSchedule(revision=2,option=0,reason='重新核对后确认安排',confirmed=True))
    with pytest.raises(ValueError): service.revise_schedule(a,identifier,ReviseSchedule(revision=3,conditions=CONDITIONS))


def test_failed_tasks_only_expose_safe_actionable_categories():
    import httpx
    from app.assistant_tasks import safe_task_failure
    exc=httpx.HTTPStatusError('secret-provider-body',request=httpx.Request('POST','https://example.invalid'),response=httpx.Response(401))
    message,code=safe_task_failure(exc)
    assert '认证失败' in message and code=='upstream_http_401' and 'secret' not in message
    assert safe_task_failure(json.JSONDecodeError('private-model-content','x',0))[1]=='invalid_model_result'
