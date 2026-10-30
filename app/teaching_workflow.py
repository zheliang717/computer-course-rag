"""Explicit question-batch -> assignment-draft handoff and real follow-through reads."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, select
from sqlalchemy.exc import IntegrityError

from app.assessment import AssessmentService
from app.models import (Assignment, AssignmentQuestion, AssignmentSubmission, AuditLog, Course,
    CourseEnrollment, QuestionBankItem, SubmissionReview, TeachingDraft)
from app.pagination import sql_page
from app.question_quality import review_question_set
from app.teacher_coach import TeacherCoachService


def utc(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


class TeachingWorkflowService:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @staticmethod
    def _draft(session, draft_id, actor_id, role, *, lock=False):
        statement = select(TeachingDraft).where(TeachingDraft.id == draft_id)
        draft = session.scalar(statement.with_for_update() if lock else statement)
        course = session.scalar(select(Course).where(Course.id == draft.course_id).with_for_update()) if draft and lock else session.get(Course, draft.course_id) if draft else None
        if not draft or not course or role not in {'teacher', 'admin'} or role != 'admin' and (
                draft.creator_id != actor_id or course.owner_id != actor_id):
            raise LookupError('题目草稿不存在或当前用户无权管理。')
        if draft.draft_type != 'question_set':
            raise ValueError('本流程仅用于结构化题目草稿。')
        return draft, course

    @staticmethod
    def _ids(draft):
        values = (draft.source_context or {}).get('published_question_ids', [])
        try:
            ids = [UUID(str(value)) for value in values] if isinstance(values, list) else []
        except (ValueError, TypeError):
            return []
        return ids if len(ids) == len(set(ids)) else []

    @staticmethod
    def _student_count(session, course_id):
        return int(session.scalar(select(func.count(CourseEnrollment.id)).where(
            CourseEnrollment.course_id == course_id, CourseEnrollment.status == 'active')) or 0)

    @staticmethod
    def _question(row):
        return {name: getattr(row, name) for name in ('question_type', 'stem', 'options', 'correct_answer',
            'explanation', 'difficulty', 'knowledge_point')}

    @staticmethod
    def _canonical(question):
        value = {key: question.get(key) for key in ('question_type', 'stem', 'options', 'correct_answer',
            'explanation', 'difficulty', 'knowledge_point')}
        for key in ('stem', 'correct_answer'):
            value[key] = str(value.get(key) or '').strip()
        value['options'] = [str(item).strip() for item in value.get('options') or [] if str(item).strip()]
        return value

    @classmethod
    def _preview(cls, session, draft, course, *, lock=False):
        ids = cls._ids(draft)
        query = select(QuestionBankItem).where(QuestionBankItem.id.in_(ids), QuestionBankItem.course_id == course.id).order_by(QuestionBankItem.id)
        rows = {row.id: row for row in session.scalars(query.with_for_update() if lock else query)}
        questions = []
        for index, question_id in enumerate(ids):
            if question_id not in rows:
                continue
            current = cls._question(rows[question_id])
            original = draft.questions[index] if index < len(draft.questions) else None
            questions.append({**current, 'question_id': str(question_id), 'position': index + 1,
                'changed_since_publication': not isinstance(original, dict) or cls._canonical(current) != cls._canonical(original)})
        problems = []
        if draft.status != 'published':
            problems.append('请先逐题审核、确认并将题目写入题库。')
        if not ids:
            problems.append('本批题目没有完整的入库关联记录，无法自动创建作业。')
        if len(rows) != len(ids):
            problems.append('部分原题已删除或不再属于本课程，不会静默跳过；请核对题库后重新准备。')
        if course.status == 'archived':
            problems.append('课程已归档，不能新建作业。')
        findings = review_question_set(questions, []) if questions else []
        if any(row['severity'] == 'error' for row in findings):
            problems.append('当前题目存在格式或重复错误，请先在题库中修正并重新预览。')
        state = {'draft_id': str(draft.id), 'status': draft.status, 'updated_at': draft.updated_at.isoformat(),
            'course_id': str(course.id), 'owner_id': str(course.owner_id), 'course_status': course.status,
            'ids': [str(value) for value in ids], 'questions': questions}
        signature = hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        title = draft.title.replace('题目草稿', '巩固作业')
        return {'draft_id': str(draft.id), 'course_id': str(course.id), 'course_title': course.title,
            'request_id': str(uuid4()), 'expected_signature': signature, 'default_title': title[:200],
            'question_count': len(ids), 'questions': questions, 'current_student_count': cls._student_count(session, course.id),
            'ready': not problems, 'problems': problems, 'findings': findings,
            'notice': '本次仅保存课程作业草稿；学生暂不可见，需另行核对并发布，不改变已有成绩。'}

    def preview(self, draft_id, *, actor_id, role):
        with self._session_factory() as session:
            draft, course = self._draft(session, draft_id, actor_id, role)
            return self._preview(session, draft, course)

    @staticmethod
    def _receipt(assignment, *, reused):
        return {'assignment_id': str(assignment.id), 'source_draft_id': str(assignment.source_draft_id),
            'course_id': str(assignment.course_id), 'title': assignment.title, 'status': assignment.status,
            'created_at': assignment.created_at, 'reused': reused}

    def create_assignment(self, draft_id, *, actor_id, actor_name, role, data):
        with self._session_factory() as session:
            draft, course = self._draft(session, draft_id, actor_id, role, lock=True)
            title = data['title'].strip()
            description = (data.get('description') or '').strip() or None
            due_at = utc(data.get('due_at'))
            if len(title) < 2:
                raise ValueError('请输入至少两个字的作业名称。')
            if data.get('confirmed') is not True:
                raise ValueError('请核对预览并明确确认保存作业草稿。')
            existing = session.scalar(select(Assignment).where(Assignment.workflow_request_id == data['request_id']))
            if existing:
                if (existing.source_draft_id != draft.id or existing.creator_id != actor_id or
                        existing.title != title or existing.description != description or utc(existing.due_at) != due_at):
                    raise ValueError('本次确认编号已用于其他内容，请重新准备预览。')
                return self._receipt(existing, reused=True)
            preview = self._preview(session, draft, course, lock=True)
            if not preview['ready']:
                raise ValueError('；'.join(preview['problems']))
            if preview['expected_signature'] != data['expected_signature']:
                raise ValueError('题目或来源状态已变化，请重新预览并核对后再保存。')
            try:
                assignment = AssessmentService.insert_assignment(session, creator_id=actor_id, data={
                    'course_id': str(course.id), 'title': title, 'description': description, 'due_at': due_at,
                    'question_ids': [row['question_id'] for row in preview['questions']], 'status': 'draft'})
                assignment.source_draft_id = draft.id
                assignment.workflow_request_id = data['request_id']
                session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action='create_assignment_from_draft',
                    resource_type='assignment', resource_id=str(assignment.id), detail={
                        'course_id': str(course.id), 'source_draft_id': str(draft.id),
                        'question_ids': [row['question_id'] for row in preview['questions']], 'status': 'draft'}))
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError('本次确认编号已使用或来源记录发生变化，请刷新关联作业后再处理。') from exc
            return self._receipt(assignment, reused=False)

    def summary(self, draft_id, *, actor_id, role):
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            draft, course = self._draft(session, draft_id, actor_id, role)
            ids = self._ids(draft)
            available = int(session.scalar(select(func.count(QuestionBankItem.id)).where(
                QuestionBankItem.id.in_(ids), QuestionBankItem.course_id == course.id)) or 0)
            counts = dict(session.execute(select(Assignment.status, func.count(Assignment.id)).where(
                Assignment.source_draft_id == draft.id, Assignment.course_id == course.id).group_by(Assignment.status)).all())
            published = (draft.source_context or {}).get('published_at')
            try:
                published_at = utc(datetime.fromisoformat(published)) if published else None
            except (TypeError, ValueError):
                published_at = None
            practice = TeacherCoachService._practice(session, course.id, None, published_at, now, ids) if published_at and ids else None
            return {'draft_id': str(draft.id), 'course_id': str(course.id), 'course_title': course.title,
                'draft_status': draft.status, 'generated_at': now, 'published_at': published_at,
                'published_question_count': len(ids), 'available_question_count': available,
                'missing_question_count': len(ids) - available, 'current_student_count': self._student_count(session, course.id),
                'linked_assignment_count': sum(counts.values()), 'assignment_statuses': counts, 'independent_practice': practice,
                'note': '独立练习和作业提交分别统计；作业成绩只纳入当前课程成员的已批改记录，未交和待批改不记零分。记录变化不证明教学因果效果。'}

    def assignments(self, draft_id, *, actor_id, role, page, page_size):
        with self._session_factory() as session:
            draft, course = self._draft(session, draft_id, actor_id, role)
            cohort = TeacherCoachService._cohort(course.id)
            current_count = self._student_count(session, course.id)
            linked = select(Assignment.id).where(Assignment.source_draft_id == draft.id, Assignment.course_id == course.id)
            active = AssignmentSubmission.student_id.in_(cohort)
            graded = AssignmentSubmission.status == 'graded'
            score = func.coalesce(SubmissionReview.score, AssignmentSubmission.score)
            totals = select(AssignmentSubmission.assignment_id.label('assignment_id'),
                func.count(AssignmentSubmission.id).label('all_submissions'),
                func.count(AssignmentSubmission.id).filter(active).label('active_submissions'),
                func.count(AssignmentSubmission.id).filter(and_(active, graded)).label('active_graded'),
                func.avg(case((and_(active, graded, AssignmentSubmission.max_score > 0),
                    score * 100.0 / func.nullif(AssignmentSubmission.max_score, 0)))).label('average_percent'))
            totals = totals.outerjoin(SubmissionReview, SubmissionReview.submission_id == AssignmentSubmission.id).where(
                AssignmentSubmission.assignment_id.in_(linked)).group_by(AssignmentSubmission.assignment_id).subquery()
            question_counts = select(AssignmentQuestion.assignment_id.label('assignment_id'), func.count(AssignmentQuestion.id).label('questions')).where(
                AssignmentQuestion.assignment_id.in_(linked)).group_by(AssignmentQuestion.assignment_id).subquery()
            query = select(Assignment, func.coalesce(totals.c.all_submissions, 0).label('all_submissions'),
                func.coalesce(totals.c.active_submissions, 0).label('active_submissions'),
                func.coalesce(totals.c.active_graded, 0).label('active_graded'), totals.c.average_percent,
                func.coalesce(question_counts.c.questions, 0).label('question_count')).outerjoin(totals, totals.c.assignment_id == Assignment.id).outerjoin(
                question_counts, question_counts.c.assignment_id == Assignment.id).where(Assignment.id.in_(linked)).order_by(Assignment.created_at.desc(), Assignment.id.desc())

            def render(row):
                item = row.Assignment
                visible = item.status in {'published', 'closed'}
                return {'id': str(item.id), 'title': item.title, 'status': item.status, 'due_at': item.due_at,
                    'created_at': item.created_at, 'question_count': int(row.question_count),
                    'current_student_count': current_count, 'active_submission_count': int(row.active_submissions),
                    'all_submission_count': int(row.all_submissions), 'graded_count': int(row.active_graded),
                    'pending_review_count': int(row.active_submissions - row.active_graded),
                    'unsubmitted_count': max(0, current_count - row.active_submissions) if visible else None,
                    'submission_percent': round(row.active_submissions / current_count * 100, 1) if visible and current_count else None,
                    'average_score_percent': round(float(row.average_percent), 1) if row.average_percent is not None else None,
                    'has_published_review': item.published_review_draft_id is not None}

            return sql_page(session, query, page=page, page_size=page_size, mapper=render, scalar=False)
