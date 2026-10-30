"""Deterministic, explainable practice mix; no claims of knowledge mastery."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math
from uuid import UUID
from sqlalchemy import select, func
from app.accounts import AccountService, utc
from app.learning_assistance import LearningAssistanceService
from app.models import (Course, CourseEnrollment, CourseSession, CoursePracticePolicy, QuestionBankItem,
    WrongQuestion, PracticeAttempt, Assignment, AssignmentQuestion, AssignmentSubmission)

DEFAULT_POLICY = {'due': 40, 'variant': 25, 'new': 20, 'taught': 15, 'interval_days': [1, 3, 7, 14, 30]}
CATEGORIES = ('due', 'variant', 'new', 'taught')


def allocate(limit, policy):
    raw = {key: limit * policy[key] / 100 for key in CATEGORIES}
    result = {key: math.floor(value) for key, value in raw.items()}
    for key in sorted(CATEGORIES, key=lambda key: (-(raw[key] - result[key]), CATEGORIES.index(key)))[:limit-sum(result.values())]:
        result[key] += 1
    return result


class PracticeRecommendationService:
    def __init__(self, sessions): self.sessions = sessions

    def policy(self, principal, course_id, data=None):
        with self.sessions.begin() as s:
            actor = AccountService.actor(s, principal, {'teacher', 'admin'} if data else None)
            LearningAssistanceService.course(s, actor, course_id)
            if data: s.scalar(select(Course).where(Course.id==course_id).with_for_update())
            row = s.scalar(select(CoursePracticePolicy).where(CoursePracticePolicy.course_id == course_id).with_for_update())
            if data:
                if (row.revision if row else 0) != data.revision: raise ValueError('练习策略已更新，请刷新后再保存。')
                if not row: row = CoursePracticePolicy(course_id=course_id, revision=0); s.add(row)
                row.settings = data.model_dump(exclude={'revision'})
                row.revision += 1; row.updated_at = datetime.now(timezone.utc)
                AccountService.audit(s, actor, 'practice_policy_saved', course_id, revision=row.revision)
            return {'course_id': str(course_id), 'revision': row.revision if row else 0, **(row.settings if row else DEFAULT_POLICY)}

    def recommend(self, student_id, course_id, limit=10, now=None):
        from app.assessment import AssessmentService
        stamp = now or datetime.now(timezone.utc)
        with self.sessions() as s:
            courses = list(s.scalars(select(Course).join(CourseEnrollment).where(CourseEnrollment.user_id == student_id,
                CourseEnrollment.status == 'active', Course.status == 'published').order_by(Course.id)))
            if course_id:
                courses = [c for c in courses if c.id == course_id]
                if not courses: raise LookupError('课程不存在或当前学生未加入该课程。')
            if not courses: return []
            ids = [c.id for c in courses]
            policies = {p.course_id: p.settings for p in s.scalars(select(CoursePracticePolicy).where(CoursePracticePolicy.course_id.in_(ids)))}
            # Do not recommend questions from unsubmitted, currently open formal work.
            submitted = select(AssignmentSubmission.assignment_id).where(AssignmentSubmission.student_id == student_id)
            reserved = select(AssignmentQuestion.question_id).join(Assignment).where(Assignment.course_id.in_(ids),
                Assignment.status == 'published', Assignment.id.not_in(submitted))
            queries = select(QuestionBankItem).where(QuestionBankItem.course_id.in_(ids), QuestionBankItem.id.not_in(reserved)).order_by(
                QuestionBankItem.difficulty, QuestionBankItem.created_at, QuestionBankItem.id).limit(5000)
            questions = list(s.scalars(queries))
            wrongs = {w.question_id: w for w in s.scalars(select(WrongQuestion).where(WrongQuestion.student_id == student_id,
                WrongQuestion.question_id.in_([q.id for q in questions])))}
            attempted = set(s.scalars(select(PracticeAttempt.question_id).where(PracticeAttempt.student_id == student_id,
                PracticeAttempt.question_id.in_([q.id for q in questions])).distinct()))
            taught = set(s.scalars(select(CourseSession.section_id).where(CourseSession.course_id.in_(ids),
                CourseSession.completed.is_(True), CourseSession.schedule_status != 'cancelled', CourseSession.section_id.is_not(None)).distinct()))
            by_course = defaultdict(list)
            for q in questions: by_course[q.course_id].append(q)
            selections = []
            for course in courses:
                policy = policies.get(course.id, DEFAULT_POLICY)
                pools = {key: [] for key in CATEGORIES}
                weak = {(q.knowledge_point or '').strip() for q in by_course[course.id] if q.id in wrongs and not wrongs[q.id].mastered}
                weak.discard('')
                for q in by_course[course.id]:
                    w = wrongs.get(q.id)
                    if w:
                        interval = policy['interval_days'][min(max(w.correct_streak, 0), len(policy['interval_days'])-1)]
                        due = utc(w.last_practiced_at) + timedelta(days=interval) if w.last_practiced_at else stamp
                        if due <= stamp:
                            pools['due'].append((q, f"{'已巩固题的间隔复习' if w.mastered else '错题到期复习'}：间隔 {interval} 天；本题历史答错 {w.wrong_count} 次。", w.retry_count))
                        continue  # Not-yet-due original mistakes never fill the other categories.
                    if (q.knowledge_point or '').strip() in weak:
                        pools['variant'].append((q, f'薄弱点变式：与未巩固错题同属“{q.knowledge_point}”，换题检验，不代表该知识点已掌握。', 0))
                    if q.id not in attempted:
                        pools['new'].append((q, '尚无本题独立练习记录，用于发现新问题；不等同从未学过此知识。', 0))
                    if q.section_id in taught:
                        pools['taught'].append((q, '教师已确认授课章节的巩固题，结合实际授课记录推荐。', 0))
                quotas, used, chosen = allocate(limit, policy), set(), []
                def take(key, count, fallback=False):
                    for q, reason, retries in pools[key]:
                        if q.id in used: continue
                        used.add(q.id)
                        row = AssessmentService._practice_item(q, priority=100-len(chosen),
                            reason=reason + (' 其他类别候选不足，作为补充。' if fallback else ''),
                            source={'due': 'spaced_review', 'variant': 'weak_variant', 'new': 'diagnostic', 'taught': 'taught_review'}[key], retry_count=retries)
                        row['policy_mix'] = {k: policy[k] for k in CATEGORIES}
                        chosen.append(row)
                        count -= 1
                        if count <= 0: break
                for key in CATEGORIES:
                    if quotas[key]: take(key, quotas[key])
                for key in CATEGORIES:
                    if len(chosen) >= limit: break
                    take(key, limit-len(chosen), True)
                selections.append(chosen)
            # Equal round-robin across enrolled courses, deterministic and duplicate-free.
            return [row for round_rows in __import__('itertools').zip_longest(*selections) for row in round_rows if row][:limit]

    def statistics(self, principal, question_id):
        with self.sessions() as s:
            actor = AccountService.actor(s, principal, {'teacher', 'admin'})
            q = s.get(QuestionBankItem, question_id)
            if not q: raise PermissionError('题目不存在。')
            AccountService.manager(s, actor, q.course_id)
            ranked = select(PracticeAttempt.is_correct.label('correct'), func.row_number().over(
                partition_by=PracticeAttempt.student_id, order_by=(PracticeAttempt.attempted_at, PracticeAttempt.id)).label('rank')).where(
                PracticeAttempt.question_id == question_id, PracticeAttempt.is_correct.is_not(None)).subquery()
            first = list(s.scalars(select(ranked.c.correct).where(ranked.c.rank == 1)))
            n, correct = len(first), sum(v is True for v in first)
            rate = correct / n if n else None
            observed = 1 if rate is not None and rate >= .85 else 2 if rate is not None and rate >= .65 else 3 if rate is not None and rate >= .45 else 4 if rate is not None and rate >= .25 else 5
            interval = None
            if n:
                z = 1.96; center = (rate + z*z/(2*n))/(1+z*z/n)
                radius = z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/(1+z*z/n)
                interval = [round(max(0, center-radius), 4), round(min(1, center+radius), 4)]
            return {'question_id': str(q.id), 'design_difficulty': q.difficulty, 'sample_students': n,
                'correct_rate': round(rate, 4) if rate is not None else None, 'observed_difficulty': observed if n >= 20 else None,
                'sample_status': 'sufficient' if n >= 20 else 'insufficient', 'wilson_95_interval': interval,
                'notice': '统计仅计每位学生首次可自动判分的独立练习，不含主观题或正式作业；少于20人不评统计难度，且不覆盖教师设计难度。'}
