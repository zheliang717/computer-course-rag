from uuid import UUID
import pytest
from app.analytics import AnalyticsService
from app.auth import principal_from_user
from app.models import User, Course, CourseEnrollment, CourseKnowledgeBase, KnowledgeBase


def test_batch_material_bindings_keep_current_role_and_course_boundaries(postgres_sessions):
    sessions=postgres_sessions
    with sessions.begin() as s:
        users=[User(username=r,display_name=r,role=r if r!='other' else 'teacher',password_hash='test',active=True,session_version=1)
            for r in ('admin','teacher','student','other')]
        s.add_all(users);s.flush()
        admin,teacher,student,other=users
        own=Course(code='OWN',title='已发布课程',status='published',owner_id=teacher.id)
        draft=Course(code='DRAFT',title='草稿课程',status='draft',owner_id=teacher.id)
        foreign=Course(code='OTHER',title='其他课程',status='published',owner_id=other.id)
        s.add_all([own,draft,foreign]);s.flush()
        for course in (own,draft,foreign):
            base=KnowledgeBase(name=course.title,course=course.title);s.add(base);s.flush()
            s.add(CourseKnowledgeBase(course_id=course.id,knowledge_base_id=base.id))
        s.add(CourseEnrollment(course_id=own.id,user_id=student.id,status='active'))
        s.add(CourseEnrollment(course_id=draft.id,user_id=student.id,status='active'))
        s.add(CourseEnrollment(course_id=foreign.id,user_id=student.id,status='inactive'))
        principals=[principal_from_user(u) for u in users]
        ids=[str(c.id) for c in (own,draft,foreign)]
    service=AnalyticsService(sessions)
    assert set(service.material_bindings(principals[0]))==set(ids)
    assert set(service.material_bindings(principals[1]))==set(ids[:2])
    assert set(service.material_bindings(principals[2]))=={ids[0]}
    assert set(service.material_bindings(principals[3]))=={ids[2]}
    with sessions.begin() as s:s.get(User,UUID(principals[2].id)).active=False
    with pytest.raises(PermissionError):service.material_bindings(principals[2])
