from datetime import timedelta
from uuid import UUID
import pytest
from sqlalchemy import select
from tests.test_practice_consistency import practice
from tests.test_account_lifecycle import setup
from app.accounts import now
from app.models import CourseSection, CourseSession, QuestionBankItem, WrongQuestion, PracticeAttempt
from app.practice_recommendations import PracticeRecommendationService, allocate, DEFAULT_POLICY
from app.practice_recommendation_routes import PracticePolicyInput


def test_mix_allocates_total_and_never_exposes_open_assignment(practice):
    _, sessions, sid, original, aid = practice
    svc = PracticeRecommendationService(sessions)
    with sessions() as s: course = s.get(QuestionBankItem, original).course_id
    assert sum(allocate(7, DEFAULT_POLICY).values()) == 7
    assert not svc.recommend(sid, course, 10)


def test_mixed_practice_due_variants_and_taught_are_distinct(practice):
    _, sessions, sid, original, aid = practice
    stamp = now()
    with sessions.begin() as s:
        course = s.get(QuestionBankItem, original).course_id
        section = CourseSection(course_id=course, title='栈与队列', position=1); s.add(section); s.flush()
        s.add(CourseSession(course_id=course, section_id=section.id, title='栈', session_date=stamp, completed=True))
        ids = []
        for index in range(8):
            q = QuestionBankItem(course_id=course, section_id=section.id, stem=f'栈例子 {index}', knowledge_point='栈', question_type='true_false', options=['正确','错误'], correct_answer='正确', difficulty=2)
            s.add(q); s.flush(); ids.append(q.id)
        s.add(WrongQuestion(student_id=sid, question_id=ids[0], mastered=False, correct_streak=0, last_practiced_at=stamp-timedelta(days=2)))
        s.add(WrongQuestion(student_id=sid, question_id=ids[1], mastered=True, correct_streak=2, last_practiced_at=stamp))
    svc = PracticeRecommendationService(sessions)
    rows = svc.recommend(sid, course, 6, stamp)
    assert len(rows) == len({q['question']['id'] for q in rows}) == 6
    assert str(original) not in {q['question']['id'] for q in rows}
    assert str(ids[1]) not in {q['question']['id'] for q in rows}
    assert {q['source'] for q in rows} == {'spaced_review', 'weak_variant', 'diagnostic', 'taught_review'}
    assert all(q['reason'] and q['question']['correct_answer'] is None for q in rows)


def test_policy_revision_and_statistics_use_first_attempt(setup):
    _, sessions, admin, teacher, course, *_ = setup
    svc = PracticeRecommendationService(sessions)
    policy = PracticePolicyInput(due=50, variant=20, new=20, taught=10, interval_days=[1,4,10], revision=0)
    assert svc.policy(teacher, course, policy)['revision'] == 1
    with pytest.raises(ValueError): svc.policy(teacher, course, policy)
    from app.models import User, CourseEnrollment
    with sessions.begin() as s:
        q = QuestionBankItem(course_id=course, stem='先进先出？', question_type='true_false', correct_answer='正确', difficulty=4); s.add(q); s.flush(); qid = q.id
        for index in range(21):
            u = User(username=f'diff_{index}', display_name='统计同学', role='student', password_hash='x'); s.add(u); s.flush()
            s.add(CourseEnrollment(course_id=course, user_id=u.id))
            s.add(PracticeAttempt(question_id=qid, student_id=u.id, answer='错误', is_correct=False, attempted_at=now()-timedelta(minutes=1)))
            s.add(PracticeAttempt(question_id=qid, student_id=u.id, answer='正确', is_correct=True, attempted_at=now()))
    stats = svc.statistics(teacher, qid)
    assert stats['sample_students'] == 21 and stats['correct_rate'] == 0
    assert stats['observed_difficulty'] == 5 and stats['design_difficulty'] == 4
