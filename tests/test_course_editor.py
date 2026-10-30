from uuid import UUID, uuid4
from copy import deepcopy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.test_account_lifecycle import setup
from app.auth import principal_from_user
from app.course_editor import CourseEditorService
from app.course_editor_routes import CourseContent, DraftInput, course_editor_router
from app.learning import LearningService
from app.models import (AuditLog, Course, CourseSection, CourseSession, KnowledgePoint,
    KnowledgeBase, CourseKnowledgeBase, CourseSectionReading, Document, QuestionBankItem, User)


def save(svc, actor, course, change):
    state = svc.get(actor, course)
    content = deepcopy(state['content']); change(content)
    return svc.save(actor, course, DraftInput(revision=state['revision'], base_signature=state['base_signature'], content=content))


def test_draft_is_private_and_publication_preserves_ids_and_schedule(setup):
    _, sessions, admin, teacher, course, *_ = setup
    svc = CourseEditorService(sessions)
    first, second = uuid4(), uuid4()
    with sessions.begin() as s:
        s.add_all([CourseSection(id=first, course_id=course, title='甲', position=1), CourseSection(id=second, course_id=course, title='乙', position=2)])
        c = s.get(Course, course); c.schedule = '周一'; c.location = '机房'
    def change(c):
        c['title'] = '新课程名'; c['learning_objectives'] = '- 理解检索'; c['assessment'] = '实验 40%'
        c['sections'].reverse(); c['sections'][0]['title'] = '乙修订'
        c['knowledge_points'].append(dict(id=str(uuid4()), name='检索', description='通过索引查找', section_id=str(second)))
    draft = save(svc, teacher, course, change)
    assert draft['has_draft'] and draft['revision'] == 1
    live = LearningService(sessions).get_course(course, user_id=UUID(teacher.id), role='teacher')
    assert live.course.title == '课程' and not live.content
    with pytest.raises(ValueError): svc.publish(teacher, course, 1, False)
    published = svc.publish(teacher, course, 1, True)
    assert not published['has_draft'] and published['revision'] == 2
    with sessions() as s:
        rows = s.scalars(select(CourseSection).where(CourseSection.course_id == course).order_by(CourseSection.position)).all()
        assert [x.id for x in rows] == [second, first]
        c = s.get(Course, course)
        assert c.title == '新课程名' and c.schedule == '周一' and c.location == '机房' and c.status == 'published'
        assert s.scalar(select(KnowledgePoint)).section_id == second
        assert s.scalar(select(AuditLog).where(AuditLog.action == 'publish_course_content'))
    assert LearningService(sessions).get_course(course, user_id=UUID(teacher.id), role='teacher').content['assessment'] == '实验 40%'


def test_versions_stale_legacy_change_and_explicit_discard(setup):
    _, sessions, _, teacher, course, *_ = setup
    svc = CourseEditorService(sessions)
    original = svc.get(teacher, course)
    draft = save(svc, teacher, course, lambda c: c.update(description='草稿介绍'))
    with pytest.raises(ValueError): svc.save(teacher, course, DraftInput(revision=0, base_signature=original['base_signature'], content=original['content']))
    LearningService(sessions).update_course(course, description='旧接口更新')
    assert svc.get(teacher, course)['stale']
    with pytest.raises(ValueError): svc.publish(teacher, course, draft['revision'], True)
    with pytest.raises(ValueError): save(svc, teacher, course, lambda c: c.update(title='误覆盖'))
    latest = svc.discard(teacher, course, draft['revision'])
    assert latest['content']['description'] == '旧接口更新' and not latest['stale']


def test_referenced_sections_and_point_names_are_not_destroyed(setup):
    _, sessions, _, teacher, course, *_ = setup
    section, point = uuid4(), uuid4()
    from app.accounts import now
    with sessions.begin() as s:
        s.add(CourseSection(id=section, course_id=course, title='重要章节', position=1)); s.flush()
        s.add(CourseSession(course_id=course, section_id=section, title='已有课次', session_date=now()))
        s.add(KnowledgePoint(id=point, course_id=course, section_id=section, name='检索'))
        s.add(QuestionBankItem(course_id=course, creator_id=UUID(teacher.id), question_type='short_answer', stem='题目', correct_answer='答案', options=[], knowledge_point='检索'))
    svc = CourseEditorService(sessions)
    draft = save(svc, teacher, course, lambda c: (c.update(sections=[]), c['knowledge_points'][0].update(section_id=None)))
    with pytest.raises(ValueError, match='不能删除'): svc.publish(teacher, course, draft['revision'], True)
    with sessions() as s: assert s.get(CourseSection, section).position == 1
    svc.discard(teacher, course, draft['revision'])
    draft = save(svc, teacher, course, lambda c: c['knowledge_points'][0].update(name='改名'))
    with pytest.raises(ValueError, match='已被题目引用'): svc.publish(teacher, course, draft['revision'], True)
    with sessions() as s: assert s.get(KnowledgePoint, point).name == '检索'


def test_owner_role_cross_course_and_library_scope(setup):
    _, sessions, admin, teacher, course, *_ = setup
    svc = CourseEditorService(sessions)
    base, foreign_section, other = uuid4(), uuid4(), uuid4()
    with sessions.begin() as s:
        outsider = User(username='outsider', display_name='其他教师', role='teacher', active=True, session_version=1, password_hash='unused')
        student = User(username='student_private', display_name='学生', role='student', active=True, session_version=1, password_hash='unused')
        s.add_all([outsider, student]); s.flush()
        outsider_p, student_p = principal_from_user(outsider), principal_from_user(student)
        s.add(Course(id=other, code='OTHER', title='其他课程', owner_id=outsider.id)); s.flush()
        s.add(CourseSection(id=foreign_section, course_id=other, title='其他章节', position=1))
        s.add(KnowledgeBase(id=base, name='其他资料', course='课程', created_by=outsider.id))
    with pytest.raises(PermissionError): svc.get(student_p, course)
    with pytest.raises(PermissionError): svc.get(outsider_p, course)
    with pytest.raises(PermissionError): save(svc, teacher, course, lambda c: c.update(owner_id=admin.id))
    with pytest.raises(PermissionError): save(svc, teacher, course, lambda c: c['sections'].append(dict(id=str(foreign_section), title='劫持', description='')))
    with pytest.raises(PermissionError): save(svc, teacher, course, lambda c: c['knowledge_base_ids'].append(str(base)))
    assert svc.libraries(teacher, course, '', 1, 5)['total'] == 0
    assert svc.libraries(admin, course, '', 1, 5)['total'] == 1
    draft = save(svc, admin, course, lambda c: c.update(owner_id=outsider_p.id))
    svc.publish(admin, course, draft['revision'], True)
    with pytest.raises(PermissionError): svc.get(teacher, course)
    assert svc.get(outsider_p, course)['content']['owner_id'] == outsider_p.id


def test_bindings_and_reading_reference_protection(setup):
    _, sessions, _, teacher, course, *_ = setup
    section, base, doc = uuid4(), uuid4(), uuid4()
    with sessions.begin() as s:
        s.add(CourseSection(id=section, course_id=course, title='章节', position=1))
        s.add(KnowledgeBase(id=base, name='学习资料', course='课程', created_by=UUID(teacher.id))); s.flush()
        s.add(CourseKnowledgeBase(course_id=course, knowledge_base_id=base))
        s.add(Document(id=doc, knowledge_base_id=base, filename='教材', status='ready')); s.flush()
        s.add(CourseSectionReading(section_id=section, document_id=doc, creator_id=UUID(teacher.id), first_page=1, last_page=2))
    svc = CourseEditorService(sessions)
    assert svc.get(teacher, course)['libraries'][0]['name'] == '学习资料'
    draft = save(svc, teacher, course, lambda c: c.update(knowledge_base_ids=[]))
    with pytest.raises(ValueError, match='章节阅读'): svc.publish(teacher, course, draft['revision'], True)
    with sessions() as s: assert s.scalar(select(CourseKnowledgeBase))


def test_http_validation_and_confirmation(setup):
    _, sessions, _, teacher, course, *_ = setup
    svc = CourseEditorService(sessions)
    api = FastAPI(); api.include_router(course_editor_router(svc, lambda: teacher)); client = TestClient(api)
    path = f'/api/v1/courses/{course}/editor'
    state = client.get(path).json()
    data = dict(revision=0, base_signature=state['base_signature'], content=state['content'])
    assert client.put(path, json={**data, 'schedule': '越权'}).status_code == 422
    assert client.put(path, json={**data, 'content': {**state['content'], 'title': '  '}}).status_code == 422
    assert client.put(path, json={**data, 'content': {**state['content'], 'cover_image_url': 'javascript:alert(1)'}}).status_code == 422
    assert client.put(path, json=data).status_code == 200
    assert client.post(path + '/publish', json=dict(revision=1)).status_code == 409
    assert client.post(path + '/publish', json=dict(revision=1, confirmed=True)).status_code == 200
    assert client.post(path + '/publish', json=dict(revision=1, confirmed=True)).status_code == 409


def test_unused_structure_delete_and_learning_plan_reference(setup):
    from app.models import StudyPlan
    _, sessions, _, teacher, course, *_ = setup
    svc = CourseEditorService(sessions)
    section, point = uuid4(), uuid4()
    draft = save(svc, teacher, course, lambda c: (c['sections'].append(dict(id=str(section), title='可编辑章节', description='')),
        c['knowledge_points'].append(dict(id=str(point), name='可编辑知识点', description='', section_id=str(section)))))
    svc.publish(teacher, course, draft['revision'], True)
    draft = save(svc, teacher, course, lambda c: c.update(sections=[], knowledge_points=[]))
    svc.publish(teacher, course, draft['revision'], True)
    with sessions() as s: assert not s.get(CourseSection, section) and not s.get(KnowledgePoint, point)
    with sessions.begin() as s:
        s.add(CourseSection(id=section, course_id=course, title='计划章节', position=1)); s.flush()
        s.add(StudyPlan(student_id=UUID(teacher.id), course_id=course, items=[dict(kind='section_preview', target_id=str(section))]))
    draft = save(svc, teacher, course, lambda c: c.update(sections=[]))
    with pytest.raises(ValueError, match='学习计划'): svc.publish(teacher, course, draft['revision'], True)


def test_simultaneous_saves_only_one_revision_wins(postgres_sessions):
    from concurrent.futures import ThreadPoolExecutor
    sessions = postgres_sessions
    with sessions.begin() as s:
        user = User(username='editor_concurrent', display_name='编辑教师', role='teacher', active=True, session_version=1, password_hash='unused')
        s.add(user); s.flush()
        actor = principal_from_user(user)
        course = Course(title='并发课程', code='CONCURRENT', owner_id=user.id); s.add(course); s.flush(); cid = course.id
    svc = CourseEditorService(sessions)
    state = svc.get(actor, cid)
    def attempt(title):
        try:
            svc.save(actor, cid, DraftInput(revision=0, base_signature=state['base_signature'], content={**state['content'], 'title': title}))
            return 'saved'
        except ValueError: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, ['甲版', '乙版'])) == ['conflict', 'saved']
    assert svc.get(actor, cid)['revision'] == 1
