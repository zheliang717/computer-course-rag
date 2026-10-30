from uuid import UUID
import pytest
from app.auth import principal_from_user
from app.learning_assistance import LearningAssistanceService
from app.learning_assistance_routes import AnnotationInput
from app.moderation import QuestionModerationService
from app.history_access import HistoryAccess
from app.models import User, Course, CourseEnrollment, KnowledgeBase, CourseKnowledgeBase, QuestionRecord, QuestionReview


def test_feedback_is_course_scoped_and_student_reads_teacher_result(postgres_sessions):
    sessions=postgres_sessions
    with sessions.begin() as s:
        users=[User(username=r,display_name=r,role=r if r!='outsider' else 'teacher',password_hash='test',active=True,session_version=1) for r in ('admin','teacher','student','outsider')]
        s.add_all(users);s.flush()
        admin,teacher,student,other=users
        c=Course(code='LOOP',title='反馈课程',owner_id=teacher.id,status='published')
        base=KnowledgeBase(name='课程资料',course='算法')
        s.add_all([c,base]);s.flush()
        s.add(CourseKnowledgeBase(course_id=c.id,knowledge_base_id=base.id))
        s.add(CourseEnrollment(course_id=c.id,user_id=student.id,status='active'))
        record=QuestionRecord(user_id=student.id,knowledge_base_id=base.id,question='算法边界',answer='😀每轮排除已经核对的中点。',message='讲解',model='offline',accepted=True,citations=[],actions=[],context_document_ids=[])
        s.add(record);s.flush()
        identifier=record.id
        principals=[principal_from_user(u) for u in users]
    a,t,u,o=principals
    service=LearningAssistanceService(sessions)
    annotation=AnnotationInput(answer_quote='每轮排除',start_offset=1,end_offset=5,category='unclear',comment='希望增加例子')
    service.annotations(u,identifier,annotation)
    assert service.review_annotations(t,identifier)['total']==1
    assert service.review_annotations(a,identifier)['total']==1
    for denied in (u,o):
        with pytest.raises(PermissionError):service.review_annotations(denied,identifier)
    with pytest.raises(PermissionError):service.annotations(t,identifier)
    moderation=QuestionModerationService(sessions,None)
    assert len(moderation.list(status='feedback',access=HistoryAccess(UUID(t.id),t.role)))==1
    assert moderation.list(status='feedback',access=HistoryAccess(UUID(o.id),o.role))==[]
    moderation.review(identifier,reviewer_id=UUID(t.id),status='rejected',revised_answer='每轮比较后排除已确认不相等的中点。',review_note='补充边界示例。',publish=False,access=HistoryAccess(UUID(t.id),t.role))
    result=service.annotations(u,identifier)['items'][0]
    assert result['review_status']=='rejected' and result['review_note']=='补充边界示例。'
    assert result['revised_answer']=='每轮比较后排除已确认不相等的中点。'
    assert result['answer_quote']=='每轮排除'  # Original immutable answer anchor survives correction.
    with sessions.begin() as s:s.get(User,UUID(t.id)).active=False
    with pytest.raises(PermissionError):service.review_annotations(t,identifier)
