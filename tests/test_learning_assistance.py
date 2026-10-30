from datetime import timedelta
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from tests.test_account_lifecycle import setup
from app.accounts import now
from app.models import (CourseSection, CourseKnowledgeBase, KnowledgeBase, Document, DocumentPage,
    AssistantTask, TeachingDraft, User)
from app.learning_assistance import LearningAssistanceService
from app.learning_assistance_routes import ReadingInput, AnnotationInput
from app.assistant_tasks import AssistantTaskService, TaskStopped
from app.teaching_drafts import TeachingDraftService
from app.chunking import chunk_document
from app.domain import SourceDocument


def test_readings_crud_requires_course_material_and_revision(setup):
    _, sessions, admin, teacher, course, *_ = setup
    section_id, base_id, document_id = uuid4(), uuid4(), uuid4()
    with sessions.begin() as s:
        s.add(CourseSection(id=section_id, course_id=course, title='二分查找', position=1))
        s.add(KnowledgeBase(id=base_id, name='课程读物', course='算法')); s.flush()
        s.add(CourseKnowledgeBase(course_id=course, knowledge_base_id=base_id))
        s.add(Document(id=document_id, knowledge_base_id=base_id, filename='算法选读', status='ready', publication_status='published')); s.flush()
        s.add_all([DocumentPage(document_id=document_id, page_number=n, content='正文') for n in (1, 2)])
    svc = LearningAssistanceService(sessions)
    data = ReadingInput(document_id=document_id, first_page=1, last_page=2, note='先理解区间边界')
    item = svc.save_reading(teacher, section_id, data)
    assert svc.readings(teacher, section_id, 1, 5)['total'] == 1
    assert item['document_name'] == '算法选读'
    with pytest.raises(ValueError): svc.save_reading(teacher, section_id, data, UUID(item['id']))
    data.revision = 1; data.note = '推演每轮中点'
    saved = svc.save_reading(teacher, section_id, data, UUID(item['id']))
    assert saved['revision'] == 2
    with pytest.raises(ValueError): svc.delete_reading(admin, section_id, UUID(item['id']), 1)
    svc.delete_reading(admin, section_id, UUID(item['id']), 2)
    assert svc.readings(teacher, section_id, 1, 5)['total'] == 0
    data.last_page = 3
    with pytest.raises(ValueError): svc.save_reading(teacher, section_id, data)


def test_annotation_is_exact_unicode_quote_not_freeform_location():
    data = AnnotationInput(answer_quote='二分🙂', start_offset=2, end_offset=5, category='calculation', comment='例子有误', source_index=1)
    LearningAssistanceService.validate_annotation('先看二分🙂的例子', data, 1)
    with pytest.raises(ValueError): LearningAssistanceService.validate_annotation('先看二分🙂的例子', data, 0)
    data.end_offset = 6
    with pytest.raises(ValueError): LearningAssistanceService.validate_annotation('先看二分🙂的例子', data, 1)


def test_teacher_tasks_replay_cancel_and_fence_atomic_draft(setup):
    _, sessions, admin, teacher, course, *_ = setup
    svc = AssistantTaskService(sessions)
    payload = {'course_id': str(course), 'draft_type': 'lesson_plan', 'topic': '边界'}
    request_id = uuid4()
    item = svc.create(teacher, request_id, payload)
    assert svc.create(teacher, request_id, payload)['id'] == item['id']
    with pytest.raises(ValueError): svc.create(teacher, request_id, {**payload, 'topic': '其他'})
    task_id, attempt, actor, _ = svc.claim()
    assert attempt == 1
    svc.action(teacher, task_id, 'cancel')
    data = {'course_id': str(course), 'draft_type': 'lesson_plan', 'title': '边界', 'content': '待审核教案', 'questions': [], 'source_context': {}}
    with pytest.raises(TaskStopped): TeachingDraftService(sessions).create(creator_id=UUID(teacher.id), data=dict(data), task_context=(svc, task_id, attempt, actor))
    with sessions() as s: assert not s.scalars(select(TeachingDraft)).all()
    svc.create(teacher, uuid4(), payload)
    task_id, attempt, actor, _ = svc.claim()
    draft = TeachingDraftService(sessions).create(creator_id=UUID(teacher.id), data=dict(data), task_context=(svc, task_id, attempt, actor))
    result = svc.get(teacher, task_id)
    assert result['status'] == 'completed' and result['result']['draft_id'] == draft['id']
    assert svc.action(teacher, task_id, 'cancel')['status'] == 'completed'
    with pytest.raises(PermissionError): svc.get(admin, task_id)


def test_teacher_task_recovery_requires_explicit_retry(setup):
    _, sessions, _, teacher, course, *_ = setup
    svc = AssistantTaskService(sessions)
    svc.create(teacher, uuid4(), {'course_id': str(course), 'draft_type': 'lesson_plan'})
    task_id, attempt, actor, _ = svc.claim()
    with sessions.begin() as s: s.get(AssistantTask, task_id).lease_expires_at = now() - timedelta(seconds=1)
    svc.recover()
    assert svc.get(teacher, task_id)['status'] == 'failed'
    assert svc.claim() is None
    svc.action(teacher, task_id, 'retry')
    assert svc.claim()[1] == attempt + 1
    with pytest.raises(TaskStopped): svc.checkpoint(actor, task_id, attempt, '迟到的旧执行')
    with sessions.begin() as s: s.get(User, UUID(teacher.id)).active = False
    with pytest.raises(PermissionError): svc.checkpoint(actor, task_id, attempt+1, '失效用户')


def test_structure_aware_chunks_keep_code_formula_and_old_strategy():
    code = '```python\nwhile left <= right:\n    mid = (left + right) // 2\n```'
    formula = '$$m = \\lfloor (l+r)/2 \\rfloor$$'
    source = SourceDocument('ds', '算法', 4, '## 二分查找\n\n' + '每轮缩小搜索范围。' * 30 + '\n\n' + code + '\n\n' + formula)
    old = chunk_document(source, chunk_size=100, overlap=20)
    new = chunk_document(source, chunk_size=100, overlap=20, structure_aware=True)
    assert old == chunk_document(source, chunk_size=100, overlap=20, structure_aware=False)
    assert any(code in c.text for c in new) and any(formula in c.text for c in new)
    assert all(c.page_number == 4 and c.metadata['chunk_strategy'] == 'structure-v1' for c in new)
