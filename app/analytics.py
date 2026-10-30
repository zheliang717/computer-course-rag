from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, case
from sqlalchemy.exc import IntegrityError

from app.models import (
    Assignment,
    AssignmentQuestion,
    AssignmentSubmission,
    ClassEnrollment,
    Course,
    CourseClass,
    CourseEnrollment,
    CourseKnowledgeBase,
    CourseSection,
    CourseSession,
    KnowledgeBase,
    KnowledgePoint,
    LearningProgress,
    QuestionBankItem,
    SubmissionReview,
    User,
    WrongQuestion,
)


class AnalyticsService:
    """Course content binding, progress tracking and role-aware learning analytics."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def ensure_defaults(self) -> None:
        with self._session_factory() as session:
            course = session.scalar(select(Course).where(Course.code == "DSA-2026"))
            if course is None:
                return
            knowledge_base = session.scalar(
                select(KnowledgeBase).where(KnowledgeBase.course == course.title).order_by(KnowledgeBase.created_at)
            ) or session.scalar(select(KnowledgeBase).order_by(KnowledgeBase.created_at))
            if knowledge_base and session.scalar(select(CourseKnowledgeBase).where(CourseKnowledgeBase.course_id == course.id, CourseKnowledgeBase.knowledge_base_id == knowledge_base.id)) is None:
                session.add(CourseKnowledgeBase(course_id=course.id, knowledge_base_id=knowledge_base.id))
            sections = list(session.scalars(select(CourseSection).where(CourseSection.course_id == course.id).order_by(CourseSection.position)).all())
            point_names = ["算法复杂度", "树与二叉树", "二叉查找树", "动态规划"]
            for index, name in enumerate(point_names):
                if session.scalar(select(KnowledgePoint).where(KnowledgePoint.course_id == course.id, KnowledgePoint.name == name)) is None:
                    session.add(KnowledgePoint(course_id=course.id, section_id=sections[min(index, len(sections) - 1)].id if sections else None, name=name))
            student = session.scalar(select(User).where(User.username == "student"))
            if student:
                for section in sections:
                    if session.scalar(select(LearningProgress).where(LearningProgress.student_id == student.id, LearningProgress.section_id == section.id)) is None:
                        session.add(LearningProgress(student_id=student.id, course_id=course.id, section_id=section.id, progress_percent=25.0 if section.position == 1 else 0.0))
            session.commit()

    def list_course_knowledge_bases(self, course_id: UUID) -> list[dict]:
        with self._session_factory() as session:
            rows = session.execute(select(KnowledgeBase).join(CourseKnowledgeBase, CourseKnowledgeBase.knowledge_base_id == KnowledgeBase.id).where(CourseKnowledgeBase.course_id == course_id).order_by(KnowledgeBase.created_at)).scalars().all()
            return [{"id": str(item.id), "name": item.name, "course": item.course, "description": item.description, "created_at": item.created_at} for item in rows]

    def material_bindings(self, principal):
        """One scoped query instead of one HTTP request per enrolled course."""
        from app.accounts import AccountService
        with self._session_factory() as session:
            actor=AccountService.actor(session,principal)
            query=select(CourseKnowledgeBase.course_id,KnowledgeBase).join(KnowledgeBase,
                KnowledgeBase.id==CourseKnowledgeBase.knowledge_base_id).join(Course,Course.id==CourseKnowledgeBase.course_id)
            if actor.role=='teacher': query=query.where(Course.owner_id==actor.id)
            elif actor.role!='admin':
                query=query.where(Course.status=='published',Course.id.in_(select(CourseEnrollment.course_id).where(
                    CourseEnrollment.user_id==actor.id,CourseEnrollment.status=='active')))
            result={}
            for course_id,item in session.execute(query.order_by(CourseKnowledgeBase.course_id,KnowledgeBase.created_at,KnowledgeBase.id)):
                result.setdefault(str(course_id),[]).append({'id':str(item.id),'name':item.name,'course':item.course,
                    'description':item.description,'created_at':item.created_at})
            return result

    def accessible_knowledge_base_ids(self, *, user_id: UUID, role: str) -> set[UUID]:
        """Return only bases attached to courses visible to this user."""
        with self._session_factory() as session:
            statement = select(CourseKnowledgeBase.knowledge_base_id).join(
                Course, Course.id == CourseKnowledgeBase.course_id
            )
            if role == "teacher":
                statement = statement.where(Course.owner_id == user_id)
            elif role == "student":
                statement = statement.join(
                    CourseEnrollment, CourseEnrollment.course_id == Course.id
                ).where(CourseEnrollment.user_id == user_id, CourseEnrollment.status == "active")
            accessible = set(session.scalars(statement.distinct()).all())
            if role == "teacher":
                accessible.update(session.scalars(
                    select(KnowledgeBase.id).where(KnowledgeBase.created_by == user_id)
                ).all())
            return accessible

    def bind_knowledge_base(self, course_id: UUID, knowledge_base_id: UUID) -> bool:
        with self._session_factory() as session:
            if session.get(Course, course_id) is None or session.get(KnowledgeBase, knowledge_base_id) is None:
                return False
            if session.scalar(select(CourseKnowledgeBase).where(CourseKnowledgeBase.course_id == course_id, CourseKnowledgeBase.knowledge_base_id == knowledge_base_id)) is None:
                session.add(CourseKnowledgeBase(course_id=course_id, knowledge_base_id=knowledge_base_id))
                session.commit()
            return True

    def list_knowledge_points(self, course_id: UUID) -> list[dict]:
        with self._session_factory() as session:
            items = session.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id).order_by(KnowledgePoint.created_at)).all()
            return [self._point_dict(item) for item in items]

    def create_knowledge_point(self, course_id: UUID, *, section_id: UUID | None, name: str, description: str | None) -> dict:
        with self._session_factory() as session:
            if session.get(Course, course_id) is None:
                raise LookupError("课程不存在。")
            if section_id:
                section = session.get(CourseSection, section_id)
                if section is None or section.course_id != course_id:
                    raise ValueError("章节不存在或不属于该课程。")
            point = KnowledgePoint(course_id=course_id, section_id=section_id, name=name.strip(), description=description)
            session.add(point)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError("该课程已经存在同名知识点。") from exc
            session.refresh(point)
            return self._point_dict(point)

    def update_progress(self, *, student_id: UUID, course_id: UUID, section_id: UUID, progress_percent: float) -> dict:
        with self._session_factory() as session:
            section = session.get(CourseSection, section_id)
            if section is None or section.course_id != course_id:
                raise LookupError("课程章节不存在。")
            progress = session.scalar(select(LearningProgress).where(LearningProgress.student_id == student_id, LearningProgress.section_id == section_id))
            if progress is None:
                progress = LearningProgress(student_id=student_id, course_id=course_id, section_id=section_id)
                session.add(progress)
            progress.progress_percent = progress_percent
            progress.last_active_at = datetime.now().astimezone()
            session.commit()
            return {"section_id": str(section.id), "section_title": section.title, "progress_percent": progress.progress_percent, "mastery_percent": progress.mastery_percent}

    def student_reports(self, student_id: UUID) -> list[dict]:
        with self._session_factory() as session:
            courses = session.scalars(select(Course).join(CourseEnrollment, CourseEnrollment.course_id == Course.id).where(
                CourseEnrollment.user_id == student_id, CourseEnrollment.status == "active")).all()
            if not courses:return []
            ids=[c.id for c in courses]
            sections=list(session.scalars(select(CourseSection).where(CourseSection.course_id.in_(ids)).order_by(CourseSection.position)))
            assignments=list(session.scalars(select(Assignment).where(Assignment.course_id.in_(ids),Assignment.status.in_(('published','closed')))))
            assignment_ids=[a.id for a in assignments]
            submissions=list(session.scalars(select(AssignmentSubmission).where(AssignmentSubmission.assignment_id.in_(assignment_ids),AssignmentSubmission.student_id==student_id))) if assignment_ids else []
            reviews={r.submission_id:r for r in session.scalars(select(SubmissionReview).where(SubmissionReview.submission_id.in_([s.id for s in submissions])))} if submissions else {}
            section_assignments={}
            if assignment_ids:
                for sid,aid in session.execute(select(QuestionBankItem.section_id,AssignmentQuestion.assignment_id)
                    .join(AssignmentQuestion,AssignmentQuestion.question_id==QuestionBankItem.id)
                    .where(AssignmentQuestion.assignment_id.in_(assignment_ids),QuestionBankItem.section_id.is_not(None)).distinct()):
                    section_assignments.setdefault(sid,set()).add(aid)
            sessions={row[0]:(int(row[1]),int(row[2])) for row in session.execute(select(CourseSession.course_id,func.count(),func.sum(case((CourseSession.completed.is_(True),1),else_=0)))
                .where(CourseSession.course_id.in_(ids)).group_by(CourseSession.course_id))}
            wrong=dict(session.execute(select(QuestionBankItem.course_id,func.count(WrongQuestion.id)).join(WrongQuestion,WrongQuestion.question_id==QuestionBankItem.id)
                .where(QuestionBankItem.course_id.in_(ids),WrongQuestion.student_id==student_id,WrongQuestion.mastered.is_(False)).group_by(QuestionBankItem.course_id)).all())
            reports=[]
            for course in courses:
                aids={a.id for a in assignments if a.course_id==course.id}
                work=[s for s in submissions if s.assignment_id in aids]
                ratios=[(reviews[s.id].score if s.id in reviews else s.score)/s.max_score*100 for s in work if s.max_score]
                average=round(sum(ratios)/len(ratios),1) if ratios else 0.0
                submitted={s.assignment_id for s in work}
                section_results=[]
                for section in (s for s in sections if s.course_id==course.id):
                    assigned=section_assignments.get(section.id,set()) & aids
                    progress=round(len(assigned & submitted)/len(assigned)*100,1) if assigned else 0.0
                    section_results.append({'section_id':str(section.id),'section_title':section.title,'progress_percent':progress,'mastery_percent':average})
                count,completed=sessions.get(course.id,(0,0))
                reports.append({'course_id':str(course.id),'course_title':course.title,
                    'progress_percent':round(completed/count*100,1) if count else 0.0,'mastery_percent':average,
                    'assignment_count':len(aids),'completed_assignments':len(work),'average_score':average,
                    'wrong_question_count':int(wrong.get(course.id,0)),'completed_sessions':completed,
                    'session_count':count,'sections':section_results})
            return reports

    def course_analytics(self, course_id: UUID) -> dict | None:
        with self._session_factory() as session:
            course = session.get(Course, course_id)
            if course is None:
                return None
            student_ids = list(session.scalars(select(CourseEnrollment.user_id).where(
                CourseEnrollment.course_id == course_id, CourseEnrollment.status == "active")).all())
            assignment_ids = list(session.scalars(select(Assignment.id).where(
                Assignment.course_id == course_id, Assignment.status.in_(("published", "closed")))).all())
            submissions = list(session.scalars(select(AssignmentSubmission).where(
                AssignmentSubmission.assignment_id.in_(assignment_ids), AssignmentSubmission.student_id.in_(student_ids))).all()) if assignment_ids and student_ids else []
            ratios = [self._effective_ratio(session, item) for item in submissions if item.max_score]
            progress_values = list(session.scalars(select(LearningProgress.progress_percent).where(
                LearningProgress.student_id.in_(student_ids), LearningProgress.course_id == course_id)).all()) if student_ids else []
            weak = []
            if student_ids:
                weak = [name for name, _ in session.execute(
                    select(QuestionBankItem.knowledge_point, func.count(WrongQuestion.id).label("count"))
                    .join(WrongQuestion, WrongQuestion.question_id == QuestionBankItem.id)
                    .where(WrongQuestion.student_id.in_(student_ids), QuestionBankItem.course_id == course_id,
                           QuestionBankItem.knowledge_point.is_not(None))
                    .group_by(QuestionBankItem.knowledge_point).order_by(func.count(WrongQuestion.id).desc()).limit(5)
                ).all()]
            denominator = len(student_ids) * len(assignment_ids)
            return {"course_id": str(course_id), "course_title": course.title, "student_count": len(student_ids),
                    "assignment_count": len(assignment_ids),
                    "submission_rate": round(len(submissions) / denominator * 100, 1) if denominator else 0.0,
                    "average_score": round(sum(ratios) / len(ratios), 1) if ratios else 0.0,
                    "average_progress": round(sum(progress_values) / len(progress_values), 1) if progress_values else 0.0,
                    "weak_knowledge_points": weak}

    def class_analytics(self, class_id: UUID) -> dict | None:
        with self._session_factory() as session:
            course_class = session.get(CourseClass, class_id)
            if course_class is None:
                return None
            course = session.get(Course, course_class.course_id)
            student_ids = list(session.scalars(select(ClassEnrollment.user_id).where(ClassEnrollment.class_id == class_id, ClassEnrollment.status == "active")).all())
            student_count = len(student_ids)
            assignment_ids = list(session.scalars(select(Assignment.id).where(
                Assignment.course_id == course_class.course_id, Assignment.status.in_(("published", "closed")))).all())
            assignment_count = len(assignment_ids)
            submissions = list(session.scalars(select(AssignmentSubmission).where(
                AssignmentSubmission.assignment_id.in_(assignment_ids), AssignmentSubmission.student_id.in_(student_ids))).all()) if assignment_ids and student_ids else []
            ratios = [self._effective_ratio(session, item) for item in submissions if item.max_score]
            progress_values = list(session.scalars(select(LearningProgress.progress_percent).where(LearningProgress.student_id.in_(student_ids), LearningProgress.course_id == course_class.course_id)).all()) if student_ids else []
            weak = []
            if student_ids:
                weak = [name for name, _ in session.execute(
                    select(QuestionBankItem.knowledge_point, func.count(WrongQuestion.id).label("count"))
                    .join(WrongQuestion, WrongQuestion.question_id == QuestionBankItem.id)
                    .where(WrongQuestion.student_id.in_(student_ids), QuestionBankItem.course_id == course_class.course_id, QuestionBankItem.knowledge_point.is_not(None))
                    .group_by(QuestionBankItem.knowledge_point).order_by(func.count(WrongQuestion.id).desc()).limit(5)
                ).all()]
            denominator = student_count * assignment_count
            return {
                "class_id": str(class_id), "class_name": course_class.name,
                "course_title": course.title if course else "课程", "student_count": student_count,
                "assignment_count": assignment_count,
                "submission_rate": round(len(submissions) / denominator * 100, 1) if denominator else 0.0,
                "average_score": round(sum(ratios) / len(ratios), 1) if ratios else 0.0,
                "average_progress": round(sum(progress_values) / len(progress_values), 1) if progress_values else 0.0,
                "weak_knowledge_points": weak,
            }

    def _student_course_report(self, session, course: Course, student_id: UUID) -> dict:
        sections = list(session.scalars(select(CourseSection).where(CourseSection.course_id == course.id).order_by(CourseSection.position)).all())
        assignment_ids = list(session.scalars(select(Assignment.id).where(
            Assignment.course_id == course.id, Assignment.status.in_(("published", "closed")))).all())
        submissions = list(session.scalars(select(AssignmentSubmission).where(AssignmentSubmission.assignment_id.in_(assignment_ids), AssignmentSubmission.student_id == student_id)).all()) if assignment_ids else []
        ratios = [self._effective_ratio(session, item) for item in submissions if item.max_score]
        average_score = round(sum(ratios) / len(ratios), 1) if ratios else 0.0
        section_results = []
        for section in sections:
            section_assignment_ids = list(session.scalars(
                select(Assignment.id).join(AssignmentQuestion, AssignmentQuestion.assignment_id == Assignment.id)
                .join(QuestionBankItem, QuestionBankItem.id == AssignmentQuestion.question_id)
                .where(Assignment.id.in_(assignment_ids), QuestionBankItem.section_id == section.id).distinct()
            ).all()) if assignment_ids else []
            completed = int(session.scalar(select(func.count(AssignmentSubmission.id)).where(
                AssignmentSubmission.student_id == student_id,
                AssignmentSubmission.assignment_id.in_(section_assignment_ids),
            )) or 0) if section_assignment_ids else 0
            section_progress = round(completed / len(section_assignment_ids) * 100, 1) if section_assignment_ids else 0.0
            section_results.append({"section_id": str(section.id), "section_title": section.title, "progress_percent": section_progress, "mastery_percent": average_score})
        session_count = int(session.scalar(select(func.count(CourseSession.id)).where(CourseSession.course_id == course.id)) or 0)
        completed_sessions = int(session.scalar(select(func.count(CourseSession.id)).where(CourseSession.course_id == course.id, CourseSession.completed.is_(True))) or 0)
        wrong_count = int(session.scalar(select(func.count(WrongQuestion.id)).join(QuestionBankItem, QuestionBankItem.id == WrongQuestion.question_id).where(WrongQuestion.student_id == student_id, QuestionBankItem.course_id == course.id, WrongQuestion.mastered.is_(False))) or 0)
        return {
            "course_id": str(course.id), "course_title": course.title,
            "progress_percent": round(completed_sessions / session_count * 100, 1) if session_count else 0.0,
            "mastery_percent": average_score, "assignment_count": len(assignment_ids),
            "completed_assignments": len(submissions), "average_score": average_score,
            "wrong_question_count": wrong_count, "completed_sessions": completed_sessions,
            "session_count": session_count, "sections": section_results,
        }

    @staticmethod
    def _point_dict(point: KnowledgePoint) -> dict:
        return {"id": str(point.id), "course_id": str(point.course_id), "section_id": str(point.section_id) if point.section_id else None, "name": point.name, "description": point.description}

    @staticmethod
    def _effective_ratio(session, submission: AssignmentSubmission) -> float:
        review = session.scalar(select(SubmissionReview).where(SubmissionReview.submission_id == submission.id))
        score = review.score if review else submission.score
        return score / submission.max_score * 100 if submission.max_score else 0.0
