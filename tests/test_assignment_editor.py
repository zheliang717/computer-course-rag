from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from tests.test_account_lifecycle import setup
from app.models import Assignment, AssignmentQuestion, AssignmentSubmission, QuestionBankItem, QuestionSource
from app.assessment import AssessmentService
from app.assignment_editor import AssignmentEditorService
from app.assignment_editor_routes import EditorInput, ForkInput, PublishInput


@pytest.fixture
def editor(setup):
    _, sessions, admin, teacher, course, *_ = setup
    with sessions.begin() as s:
        q = QuestionBankItem(course_id=course, stem='栈遵循先进先出？', question_type='true_false', options=['正确','错误'], correct_answer='错误', explanation='栈后进先出', difficulty=2)
        s.add(q); s.flush(); qid = q.id
        a = Assignment(course_id=course, title='栈课堂练习', status='draft', creator_id=UUID(teacher.id)); s.add(a); s.flush(); aid = a.id
        s.add(AssignmentQuestion(assignment_id=aid, question_id=qid, points=10, position=1))
    return AssignmentEditorService(sessions), sessions, teacher, aid, qid


def test_draft_full_edit_preview_stale_and_publication(editor):
    svc, sessions, teacher, aid, qid = editor
    preview = svc.preview(teacher, aid)
    data = EditorInput(revision=1, title='新版栈作业', ai_policy='disabled', reason='调整分值', questions=[{'question_id': qid, 'points': 7.5}])
    saved = svc.save(teacher, aid, data)
    assert saved['revision'] == 2 and saved['questions'][0]['points'] == 7.5
    with pytest.raises(ValueError): svc.save(teacher, aid, data)
    with pytest.raises(ValueError): svc.publish(teacher, aid, PublishInput(signature=preview['signature'], confirmed=True))
    current = svc.preview(teacher, aid)
    result = svc.publish(teacher, aid, PublishInput(signature=current['signature'], confirmed=True))
    assert result['status'] == 'published'
    with pytest.raises(ValueError): svc.save(teacher, aid, data.model_copy(update={'revision': result['revision']}))
    assert svc.history(teacher, aid, 1, 5)['total'] == 3


def test_question_edit_clones_bank_and_fork_preserves_original(editor):
    svc, sessions, teacher, aid, qid = editor
    with sessions.begin() as s:
        s.add(QuestionSource(question_id=qid,source={'title':'原题选读','spans':[{'page_number':2,'quote':'原题文字'}]}))
    new_content = {'question_type': 'true_false', 'stem': '队列遵循先进先出？', 'options':['正确','错误'], 'correct_answer':'正确', 'explanation':'队列先入先出', 'difficulty':2}
    data = EditorInput(revision=1, title='队列练习', reason='替换本题', questions=[{'question_id':qid, 'points':20, 'content':new_content}])
    draft = svc.save(teacher, aid, data)
    new_id = UUID(draft['questions'][0]['question_id'])
    assert new_id != qid
    with sessions() as s:
        assert s.get(QuestionBankItem, qid).correct_answer == '错误'
        origin=s.get(QuestionSource,new_id).source
        assert origin['title']=='原题选读' and origin['spans'][0]['page_number']==2
        assert origin['revision_of_question_id']==str(qid)
    preview = svc.preview(teacher, aid); svc.publish(teacher, aid, PublishInput(signature=preview['signature'],confirmed=True))
    request = ForkInput(request_id=uuid4())
    fork = svc.fork(teacher, aid, request)
    assert svc.fork(teacher, aid, request)['id'] == fork['id']
    assert fork['status'] == 'draft' and fork['previous_version_id'] == str(aid)
    with sessions() as s:
        assert s.get(Assignment, aid).status == 'published'
        assert s.scalar(select(AssignmentQuestion.points).where(AssignmentQuestion.assignment_id == aid)) == 20
    with pytest.raises(ValueError): AssessmentService(sessions).update_assignment_status(aid,status='draft',user_id=UUID(teacher.id),role='teacher')


def test_editor_rejects_foreign_bank_question_atomically(editor):
    svc, sessions, teacher, aid, qid = editor
    with pytest.raises(ValueError): svc.save(teacher,aid,EditorInput(revision=1,title='不应保存',reason='错误题目',questions=[{'question_id':uuid4(),'points':10}]))
    state = svc.get(teacher,aid)
    assert state['revision'] == 1 and state['title'] == '栈课堂练习'
    assert svc.history(teacher,aid,1,5)['total'] == 0
