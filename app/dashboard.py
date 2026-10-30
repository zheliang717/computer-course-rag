"""Read-only, course-scoped home statistics and SQL-paged teaching work."""
from datetime import datetime, timezone

from sqlalchemy import and_, case, exists, func, or_, select

from app.models import (
    Assignment, AssignmentSubmission, Chunk, ClassEnrollment, Course, CourseClass,
    CourseEnrollment, CourseKnowledgeBase, Document, KnowledgeBase, LateSubmissionRequest,
    QuestionBankItem, User,
)
from app.pagination import sql_page


class DashboardService:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @staticmethod
    def _courses(user_id, role):
        statement = select(Course.id)
        if role == 'teacher':
            return statement.where(Course.owner_id == user_id)
        if role == 'student':
            return statement.where(Course.id.in_(select(CourseEnrollment.course_id).where(
                CourseEnrollment.user_id == user_id, CourseEnrollment.status == 'active')))
        if role != 'admin':
            raise PermissionError('当前角色不能访问首页统计。')
        return statement

    @classmethod
    def _members(cls, user_id, role):
        # Match course-cohort analysis: active membership + current student role; login disablement is separate.
        return select(CourseEnrollment.course_id, CourseEnrollment.user_id).join(
            User, User.id == CourseEnrollment.user_id).where(
            CourseEnrollment.status == 'active', User.role == 'student',
            CourseEnrollment.course_id.in_(cls._courses(user_id, role))).subquery('home_members')

    @classmethod
    def _teaching_work(cls, user_id, role, now):
        if role not in {'teacher', 'admin'}:
            raise PermissionError('教学待办仅供教师和管理员查看。')
        members = cls._members(user_id, role)
        member_match = and_(members.c.course_id == Assignment.course_id,
                            members.c.user_id == AssignmentSubmission.student_id)
        submissions = select(AssignmentSubmission.assignment_id,
            func.count(AssignmentSubmission.id).label('submission_count'),
            func.sum(case((AssignmentSubmission.status != 'graded', 1), else_=0)).label('pending_review_count'),
        ).join(Assignment, Assignment.id == AssignmentSubmission.assignment_id).join(
            members, member_match).group_by(AssignmentSubmission.assignment_id).subquery('home_submissions')
        late = select(LateSubmissionRequest.assignment_id,
            func.count(LateSubmissionRequest.id).label('pending_late_count'),
        ).join(Assignment, Assignment.id == LateSubmissionRequest.assignment_id).join(members, and_(
            members.c.course_id == Assignment.course_id, members.c.user_id == LateSubmissionRequest.student_id),
        ).where(LateSubmissionRequest.status == 'pending').group_by(
            LateSubmissionRequest.assignment_id).subquery('home_late')
        missed = select(Assignment.id.label('assignment_id'),
            func.count(members.c.user_id).label('overdue_unsubmitted_count'),
        ).join(members, members.c.course_id == Assignment.course_id).outerjoin(
            AssignmentSubmission, and_(AssignmentSubmission.assignment_id == Assignment.id,
                                      AssignmentSubmission.student_id == members.c.user_id),
        ).where(Assignment.due_at <= now, AssignmentSubmission.id.is_(None)).group_by(
            Assignment.id).subquery('home_missed')
        sizes = select(members.c.course_id, func.count().label('student_count')).group_by(
            members.c.course_id).subquery('home_course_sizes')
        return select(
            Assignment.id.label('assignment_id'), Assignment.course_id,
            Assignment.title.label('assignment_title'), Course.title.label('course_title'),
            Course.code.label('course_code'), Assignment.due_at,
            func.coalesce(sizes.c.student_count, 0).label('student_count'),
            func.coalesce(submissions.c.submission_count, 0).label('submission_count'),
            func.coalesce(submissions.c.pending_review_count, 0).label('pending_review_count'),
            func.coalesce(late.c.pending_late_count, 0).label('pending_late_count'),
            func.coalesce(missed.c.overdue_unsubmitted_count, 0).label('overdue_unsubmitted_count'),
        ).select_from(Assignment).join(Course, Course.id == Assignment.course_id).outerjoin(
            submissions, submissions.c.assignment_id == Assignment.id).outerjoin(
            late, late.c.assignment_id == Assignment.id).outerjoin(
            missed, missed.c.assignment_id == Assignment.id).outerjoin(
            sizes, sizes.c.course_id == Assignment.course_id).where(
            Assignment.course_id.in_(cls._courses(user_id, role)),
            Assignment.status.in_(('published', 'closed')))

    def summary(self, *, user_id, role):
        now = datetime.now(timezone.utc)
        allowed = self._courses(user_id, role)
        with self._session_factory() as session:
            count = lambda statement: int(session.scalar(statement) or 0)
            values = {
                'role': role, 'as_of': now,
                'course_count': count(select(func.count(Course.id)).where(Course.id.in_(allowed))),
                'question_count': count(select(func.count(QuestionBankItem.id)).where(QuestionBankItem.course_id.in_(allowed))),
                'recent_course_ids': list(session.scalars(select(Course.id).where(Course.id.in_(allowed)).order_by(
                    Course.created_at.desc(), Course.id.desc()).limit(3)).all()),
                'student_count': 0, 'course_membership_count': 0, 'pending_tasks': 0,
                'pending_review_count': 0, 'pending_late_count': 0, 'overdue_unsubmitted_count': 0,
            }
            # Legacy field retained for old clients; it does not drive course member statistics.
            legacy = select(func.count(CourseClass.id))
            if role == 'teacher':
                legacy = legacy.where(CourseClass.teacher_id == user_id)
            elif role == 'student':
                legacy = legacy.where(CourseClass.id.in_(select(ClassEnrollment.class_id).where(
                    ClassEnrollment.user_id == user_id, ClassEnrollment.status == 'active')))
            values['class_count'] = count(legacy)
            knowledge = select(CourseKnowledgeBase.knowledge_base_id).where(CourseKnowledgeBase.course_id.in_(allowed))
            visible_bases = select(KnowledgeBase.id)
            if role != 'admin':
                conditions = [KnowledgeBase.id.in_(knowledge)]
                if role == 'teacher':
                    conditions.append(KnowledgeBase.created_by == user_id)
                visible_bases = visible_bases.where(or_(*conditions))
            values['document_count'] = count(select(func.count(Document.id)).where(Document.knowledge_base_id.in_(visible_bases)))
            values['indexed_chunk_count'] = count(select(func.count(Chunk.id)).join(
                Document, Document.id == Chunk.document_id).where(Document.knowledge_base_id.in_(visible_bases)))
            if role == 'student':
                unanswered = select(Assignment.id).where(Assignment.course_id.in_(allowed),
                    Assignment.status == 'published', ~exists(select(AssignmentSubmission.id).where(
                        AssignmentSubmission.assignment_id == Assignment.id, AssignmentSubmission.student_id == user_id)))
                values['pending_tasks'] = count(select(func.count()).select_from(unanswered.subquery()))
            else:
                members = self._members(user_id, role)
                values['student_count'] = count(select(func.count(func.distinct(members.c.user_id))))
                values['course_membership_count'] = count(select(func.count()).select_from(members))
                work = self._teaching_work(user_id, role, now).subquery('home_work')
                fields = ('pending_review_count', 'pending_late_count', 'overdue_unsubmitted_count')
                row = session.execute(select(*[func.coalesce(func.sum(work.c[field]), 0) for field in fields])).one()
                values.update({field: int(value) for field, value in zip(fields, row)})
                values['pending_tasks'] = values['pending_review_count'] + values['pending_late_count']
            return values

    def teaching_tasks(self, *, user_id, role, kind, page, page_size, query=''):
        keys = {'review': 'pending_review_count', 'late': 'pending_late_count', 'overdue': 'overdue_unsubmitted_count'}
        if kind not in keys:
            raise ValueError('待办类型不支持。')
        work = self._teaching_work(user_id, role, datetime.now(timezone.utc)).subquery('home_work')
        column = work.c[keys[kind]]
        statement = select(work).where(column > 0)
        if query.strip():
            statement = statement.where(or_(work.c.assignment_title.icontains(query.strip(), autoescape=True),
                                           work.c.course_title.icontains(query.strip(), autoescape=True)))
        statement = statement.order_by(column.desc(), work.c.due_at.asc().nullslast(), work.c.assignment_id)
        def view(row):
            values = dict(row._mapping)
            values['assignment_id'], values['course_id'] = str(values['assignment_id']), str(values['course_id'])
            return values
        with self._session_factory() as session:
            return sql_page(session, statement, page=page, page_size=page_size, mapper=view, scalar=False)
