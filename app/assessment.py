from __future__ import annotations

import json
import hashlib
import math
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, or_, select, case
from sqlalchemy.exc import IntegrityError

from app.models import (
    Assignment,
    AssignmentQuestion,
    AssignmentSubmission,
    AuditLog,
    ClassEnrollment,
    Course,
    CourseClass,
    CourseEnrollment,
    CourseSection,
    LateSubmissionRequest,
    PracticeAttempt,
    PracticeSubmissionReceipt,
    QuestionBankItem,
    SubmissionReview,
    User,
    WrongQuestion,
)


from app.pagination import sql_page


class QuestionInUseError(ValueError):
    """Prevent edits that would rewrite an assignment or practice history."""


class SubmissionConflictError(ValueError):
    """The grading baseline changed before this edit acquired its row lock."""


class AssessmentService:
    """Question bank, assignments, auto grading and wrong-question workflow."""

    @staticmethod
    def _lock_student(session, student_id):
        # Shared by assignment and practice writes so the same mistake cannot
        # race with a retry. PostgreSQL serializes on this existing owner row.
        student = session.scalar(select(User).where(User.id == student_id).with_for_update())
        if student is None or not student.active or student.role != 'student':
            raise LookupError('学生账号不存在或当前不可提交。')

    @staticmethod
    def _record_mistake(session, student_id, question_id, answer, wrong=None):
        if wrong is None:
            wrong = session.scalar(select(WrongQuestion).where(WrongQuestion.student_id == student_id, WrongQuestion.question_id == question_id))
        if wrong is None:
            wrong = WrongQuestion(student_id=student_id, question_id=question_id, wrong_count=1, retry_count=0)
            session.add(wrong)
        else:
            wrong.wrong_count += 1
        wrong.last_answer = answer
        wrong.correct_streak = 0
        wrong.mastered = False
        return wrong

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

    def ensure_defaults(self) -> None:
        with self._session_factory() as session:
            course = session.scalar(select(Course).where(Course.code == "DSA-2026"))
            teacher = session.scalar(select(User).where(User.username == "teacher"))
            course_class = session.scalar(select(CourseClass).where(CourseClass.invite_code == "DS2026"))
            if course is None or course_class is None:
                return
            existing = session.scalar(select(func.count(QuestionBankItem.id)).where(QuestionBankItem.course_id == course.id))
            if not existing:
                section = session.scalar(
                    select(CourseSection).where(CourseSection.course_id == course.id).order_by(CourseSection.position)
                )
                seeds = [
                    ("算法复杂度通常使用什么符号描述增长上界？", ["Ω", "Θ", "O", "λ"], "O", "大 O 记号表示渐进上界。", "算法复杂度"),
                    ("二叉查找树的左子树所有关键字都小于根节点。", ["正确", "错误"], "正确", "这是二叉查找树的基本性质。", "二叉查找树"),
                    ("动态规划适用问题通常具备哪两个关键性质？", [], "最优子结构和重叠子问题", "动态规划通过保存重叠子问题结果，并由最优子结构组合全局最优解。", "动态规划"),
                ]
                for index, (stem, options, answer, explanation, point) in enumerate(seeds):
                    session.add(
                        QuestionBankItem(
                            course_id=course.id,
                            section_id=section.id if section else None,
                            creator_id=teacher.id if teacher else None,
                            question_type="single_choice" if index == 0 else "true_false" if index == 1 else "short_answer",
                            stem=stem,
                            options=options,
                            correct_answer=answer,
                            explanation=explanation,
                            difficulty=index + 1,
                            knowledge_point=point,
                        )
                    )
                session.flush()
            assignment = session.scalar(select(Assignment).where(Assignment.class_id == course_class.id, Assignment.title == "数据结构基础诊断练习"))
            if assignment is None:
                assignment = Assignment(
                    course_id=course.id,
                    class_id=course_class.id,
                    creator_id=teacher.id if teacher else None,
                    title="数据结构基础诊断练习",
                    description="完成三道基础题，系统会自动评分并将错题加入错题本。",
                    status="published",
                )
                session.add(assignment)
                session.flush()
                questions = list(session.scalars(select(QuestionBankItem).where(QuestionBankItem.course_id == course.id).order_by(QuestionBankItem.created_at)).all())
                for position, question in enumerate(questions[:3], 1):
                    session.add(AssignmentQuestion(assignment_id=assignment.id, question_id=question.id, position=position, points=10.0))
            session.commit()

    @staticmethod
    def question_dict(question: QuestionBankItem, *, reveal_answer: bool) -> dict:
        return {
            "id": str(question.id), "course_id": str(question.course_id),
            "section_id": str(question.section_id) if question.section_id else None,
            "question_type": question.question_type, "stem": question.stem,
            "options": question.options or [],
            "correct_answer": question.correct_answer if reveal_answer else None,
            "explanation": question.explanation if reveal_answer else None,
            "difficulty": question.difficulty, "knowledge_point": question.knowledge_point,
        }

    @staticmethod
    def _question_scope(user_id: UUID, role: str):
        statement = select(QuestionBankItem)
        if role == "teacher":
            statement = statement.join(Course, Course.id == QuestionBankItem.course_id).where(Course.owner_id == user_id)
        elif role == "student":
            statement = statement.join(CourseEnrollment, CourseEnrollment.course_id == QuestionBankItem.course_id).where(
                CourseEnrollment.user_id == user_id, CourseEnrollment.status == "active")
        return statement

    def list_questions(self, *, course_id: UUID | None, user_id: UUID, role: str) -> list[dict]:
        with self._session_factory() as session:
            statement = self._question_scope(user_id, role)
            if course_id:
                statement = statement.where(QuestionBankItem.course_id == course_id)
            statement = statement.order_by(QuestionBankItem.created_at.desc(), QuestionBankItem.id.desc())
            return [self.question_dict(item, reveal_answer=role in {"teacher", "admin"}) for item in session.scalars(statement).all()]

    def list_questions_page(self, *, course_id: UUID | None, user_id: UUID, role: str,
                            keyword: str | None, question_type: str | None, page: int, page_size: int,
                            section_id:UUID|None=None,difficulty:int|None=None) -> dict:
        with self._session_factory() as session:
            statement = self._question_scope(user_id, role)
            if course_id:
                statement = statement.where(QuestionBankItem.course_id == course_id)
            if question_type:
                statement = statement.where(QuestionBankItem.question_type == question_type)
            if section_id: statement=statement.where(QuestionBankItem.section_id==section_id)
            if difficulty: statement=statement.where(QuestionBankItem.difficulty==difficulty)
            if keyword and keyword.strip():
                term = keyword.strip()
                statement = statement.where(or_(
                    QuestionBankItem.stem.icontains(term, autoescape=True),
                    QuestionBankItem.knowledge_point.icontains(term, autoescape=True),
                ))
            total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            items = session.scalars(statement.order_by(
                QuestionBankItem.created_at.desc(), QuestionBankItem.id.desc(),
            ).offset((page - 1) * page_size).limit(page_size)).all()
            return {"items": [self.question_dict(item, reveal_answer=role in {"teacher", "admin"}) for item in items],
                    "total": total, "page": page, "page_size": page_size}

    def get_question(self, question_id: UUID, *, user_id: UUID, role: str) -> dict | None:
        with self._session_factory() as session:
            statement = self._question_scope(user_id, role).where(QuestionBankItem.id == question_id)
            question = session.scalar(statement)
            return self.question_dict(question, reveal_answer=role in {"teacher", "admin"}) if question else None

    @staticmethod
    def _question_is_used(session, question_id: UUID) -> bool:
        return any(session.scalar(select(model.id).where(model.question_id == question_id).limit(1)) is not None
                   for model in (AssignmentQuestion, PracticeAttempt, WrongQuestion))

    def update_question(self, question_id: UUID, *, actor_id: UUID, actor_name: str,
                        role: str, changes: dict) -> dict | None:
        with self._session_factory() as session:
            question = session.scalar(select(QuestionBankItem).where(QuestionBankItem.id == question_id).with_for_update())
            if question is None:
                return None
            course = session.get(Course, question.course_id)
            if role == "teacher" and (course is None or course.owner_id != actor_id):
                return None
            if self._question_is_used(session, question_id):
                raise QuestionInUseError("题目已被作业或练习使用；为保留历史成绩，请新建修订题目。")
            question_type = changes.get("question_type", question.question_type)
            options = [str(value).strip() for value in (changes.get("options", question.options) or []) if str(value).strip()]
            if question_type in {"fill_blank", "short_answer"} and "options" not in changes:
                options = []
            answer = changes.get("correct_answer", question.correct_answer)
            stem = changes.get("stem", question.stem)
            if question_type not in {"single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer"}:
                raise ValueError("题型不支持。")
            if not isinstance(stem, str) or len(stem.strip()) < 2 or not isinstance(answer, str) or not answer.strip():
                raise ValueError("题干和参考答案不能为空。")
            if question_type in {"single_choice", "multiple_choice", "true_false"} and len(options) < 2:
                raise ValueError("选择题、判断题或多选题至少需要两个选项。")
            if question_type == "multiple_choice" and len(self._split_multiple(answer)) < 2:
                raise ValueError("多选题至少需要两个正确答案，使用逗号分隔。")
            if changes.get("difficulty", question.difficulty) is None:
                raise ValueError("难度不能为空。")
            if "section_id" in changes:
                try:
                    section_id = UUID(str(changes["section_id"])) if changes["section_id"] else None
                except ValueError as exc:
                    raise ValueError("section_id 必须是有效的 UUID。") from exc
                if section_id and not session.scalar(select(CourseSection.id).where(
                    CourseSection.id == section_id, CourseSection.course_id == question.course_id)):
                    raise ValueError("章节不属于该课程。")
                question.section_id = section_id
            question.question_type = question_type
            question.options = options
            question.stem = stem.strip()
            question.correct_answer = answer.strip()
            for field in ("explanation", "difficulty", "knowledge_point"):
                if field in changes:
                    setattr(question, field, changes[field])
            session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action="update_question",
                                 resource_type="question", resource_id=str(question_id),
                                 detail={"course_id": str(question.course_id), "changed_fields": sorted(changes)}))
            session.commit()
            return self.question_dict(question, reveal_answer=True)

    def delete_question(self, question_id: UUID, *, actor_id: UUID, actor_name: str, role: str) -> bool:
        with self._session_factory() as session:
            question = session.scalar(select(QuestionBankItem).where(QuestionBankItem.id == question_id).with_for_update())
            if question is None:
                return False
            course = session.get(Course, question.course_id)
            if role == "teacher" and (course is None or course.owner_id != actor_id):
                return False
            if self._question_is_used(session, question_id):
                raise QuestionInUseError("题目已被作业或练习使用，不能删除历史题目。")
            session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action="delete_question",
                                 resource_type="question", resource_id=str(question_id),
                                 detail={"course_id": str(question.course_id), "stem": question.stem,
                                         "question_type": question.question_type}))
            session.delete(question)
            session.commit()
            return True

    def create_question(self, *, creator_id: UUID, data: dict) -> dict:
        with self._session_factory() as session:
            course_id = UUID(data["course_id"])
            if session.get(Course, course_id) is None:
                raise LookupError("课程不存在。")
            section_id = UUID(data["section_id"]) if data.get("section_id") else None
            if section_id and not session.scalar(select(CourseSection.id).where(
                CourseSection.id == section_id, CourseSection.course_id == course_id)):
                raise ValueError("章节不属于该课程。")
            question_type = data["question_type"]
            options = [str(value).strip() for value in data["options"] if str(value).strip()]
            if question_type in {"single_choice", "multiple_choice", "true_false"} and len(options) < 2:
                raise ValueError("选择题、判断题或多选题至少需要两个选项。")
            if question_type == "multiple_choice" and len(self._split_multiple(data["correct_answer"])) < 2:
                raise ValueError("多选题至少需要两个正确答案，使用逗号分隔。")
            if question_type == "fill_blank" and not data["correct_answer"].strip():
                raise ValueError("填空题必须提供答案；多个空使用 || 分隔。")
            question = QuestionBankItem(
                course_id=course_id,
                section_id=section_id,
                creator_id=creator_id,
                question_type=question_type, stem=data["stem"].strip(), options=options,
                correct_answer=data["correct_answer"].strip(), explanation=data.get("explanation"),
                difficulty=data["difficulty"], knowledge_point=data.get("knowledge_point"),
            )
            session.add(question)
            session.commit()
            session.refresh(question)
            return self.question_dict(question, reveal_answer=True)

    def create_assignment(self, *, creator_id: UUID, data: dict) -> dict:
        with self._session_factory() as session:
            assignment = self.insert_assignment(session, creator_id=creator_id, data=data)
            session.commit()
            return self._assignment_dict(session, assignment, user_id=creator_id)

    @staticmethod
    def insert_assignment(session, *, creator_id: UUID, data: dict) -> Assignment:
        """Common insertion rules; the caller owns the transaction and its audit."""
        course_class = session.get(CourseClass, UUID(data["class_id"])) if data.get("class_id") else None
        if data.get("class_id") and course_class is None:
            raise LookupError("原班级不存在。")
        course_id = UUID(data["course_id"]) if data.get("course_id") else course_class.course_id if course_class else None
        course = session.get(Course, course_id) if course_id else None
        if course is None:
            raise LookupError("课程不存在。")
        if course_class and course_class.course_id != course.id:
            raise ValueError("班级与课程不一致。")
        question_ids = [UUID(value) for value in data["question_ids"]]
        questions = list(session.scalars(select(QuestionBankItem).where(QuestionBankItem.id.in_(question_ids))).all())
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("同一作业不能重复选择题目。")
        if len(questions) != len(question_ids) or any(q.course_id != course.id for q in questions):
            raise ValueError("题目不存在或不属于该课程。")
        if course_class is None and data.get("status") not in (None, "draft"):
            raise ValueError("课程作业必须先保存为草稿，再由教师确认发布。")
        assignment = Assignment(course_id=course.id, class_id=course_class.id if course_class else None,
            creator_id=creator_id, title=data["title"].strip(), description=data.get("description"),
            due_at=data.get("due_at"), status=data.get("status") or ("published" if course_class else "draft"))
        session.add(assignment)
        session.flush()
        for position, question_id in enumerate(question_ids, 1):
            session.add(AssignmentQuestion(assignment_id=assignment.id, question_id=question_id, position=position, points=10.0))
        return assignment

    def list_assignments(self, *, user_id: UUID, role: str, course_id: UUID | None = None, page: int | None = None, page_size: int = 10,
                         task_view: str = 'all', keyword: str = '', with_counts: bool = False) -> list[dict] | dict:
        with self._session_factory() as session:
            statement = select(Assignment).join(Course, Course.id == Assignment.course_id)
            if course_id is not None: statement = statement.where(Assignment.course_id == course_id)
            if role == "teacher":
                statement = statement.where(Course.owner_id == user_id)
            elif role == "student":
                enrolled_courses = select(CourseEnrollment.course_id).where(
                    CourseEnrollment.user_id == user_id, CourseEnrollment.status == "active")
                statement = statement.where(Assignment.course_id.in_(enrolled_courses), Assignment.status.in_(("published", "closed")))
            if keyword.strip(): statement=statement.where(or_(Assignment.title.contains(keyword.strip(),autoescape=True),Course.title.contains(keyword.strip(),autoescape=True)))
            now=datetime.now(timezone.utc)
            own_submission=select(AssignmentSubmission.id).where(AssignmentSubmission.assignment_id==Assignment.id,AssignmentSubmission.student_id==user_id).exists()
            extension=select(LateSubmissionRequest.id).where(LateSubmissionRequest.assignment_id==Assignment.id,LateSubmissionRequest.student_id==user_id,
                LateSubmissionRequest.status=='approved',or_(LateSubmissionRequest.approved_until.is_(None),LateSubmissionRequest.approved_until>=now)).exists()
            ready=(Assignment.status=='published') & ~own_submission & or_(Assignment.due_at.is_(None),Assignment.due_at>=now,extension)
            filters={'all':True,'todo':ready,'late':~own_submission & ~ready,'submitted':own_submission} if role=='student' else {
                'all':True,'draft':Assignment.status=='draft',
                'active':(Assignment.status=='published') & or_(Assignment.due_at.is_(None),Assignment.due_at>=now),
                'grading':(Assignment.status!='draft') & select(AssignmentSubmission.id).where(AssignmentSubmission.assignment_id==Assignment.id,AssignmentSubmission.status!='graded').exists(),
                'ended':or_(Assignment.status=='closed',(Assignment.status=='published') & (Assignment.due_at<now))}
            if task_view not in filters: raise ValueError('当前角色不支持该作业视图。')
            counts={key:int(session.scalar(select(func.count()).select_from(statement.where(condition).subquery())) or 0) for key,condition in filters.items()} if with_counts else {}
            statement=statement.where(filters[task_view])
            if task_view=='todo': statement=statement.order_by(Assignment.due_at.asc().nulls_last(),Assignment.created_at.desc(),Assignment.id.desc())
            else: statement = statement.order_by(Assignment.created_at.desc(), Assignment.id.desc())
            if page is not None:
                result=sql_page(session, statement, page=page, page_size=page_size,
                                mapper=lambda item:item)
                result['items']=self._assignment_dicts(session,result['items'],user_id)
                if with_counts: result['counts']=counts
                return result
            assignments = list(session.scalars(statement).all())
            return self._assignment_dicts(session,assignments,user_id)

    def get_assignment(self, assignment_id: UUID, *, user_id: UUID, role: str) -> dict | None:
        with self._session_factory() as session:
            assignment = session.get(Assignment, assignment_id)
            if assignment is None or not self._can_access_assignment(session, assignment, user_id, role):
                return None
            result = self._assignment_dict(session, assignment, user_id=user_id)
            links = list(session.scalars(select(AssignmentQuestion).where(AssignmentQuestion.assignment_id == assignment.id).order_by(AssignmentQuestion.position)).all())
            submitted = session.scalar(select(AssignmentSubmission).where(AssignmentSubmission.assignment_id == assignment.id, AssignmentSubmission.student_id == user_id))
            result["questions"] = [self.question_dict(
                session.get(QuestionBankItem, link.question_id),
                reveal_answer=role != "student" or (submitted is not None and submitted.status == "graded"),
            ) for link in links]
            return result

    def submit(self, assignment_id: UUID, *, student_id: UUID, answers: dict[str, str]) -> dict:
        with self._session_factory() as session:
            self._lock_student(session, student_id)
            assignment = session.get(Assignment, assignment_id)
            if assignment is None or not self._can_access_assignment(session, assignment, student_id, "student"):
                raise LookupError("作业不存在或不可访问。")
            if assignment.status != "published":
                raise ValueError("作业当前不可提交。")
            if session.scalar(select(AssignmentSubmission.id).where(
                AssignmentSubmission.assignment_id == assignment.id,
                AssignmentSubmission.student_id == student_id,
            )) is not None:
                raise ValueError("作业已经提交，不能重复提交。")
            now = datetime.now(timezone.utc)
            late_request = None
            if assignment.due_at and now > self._utc(assignment.due_at):
                late_request = session.scalar(select(LateSubmissionRequest).where(
                    LateSubmissionRequest.assignment_id == assignment.id,
                    LateSubmissionRequest.student_id == student_id,
                    LateSubmissionRequest.status == "approved",
                ))
                if late_request is None or (late_request.approved_until and now > self._utc(late_request.approved_until)):
                    raise ValueError("作业已经截止，请先申请并获得教师补交批准。")
            links = list(session.scalars(select(AssignmentQuestion).where(AssignmentQuestion.assignment_id == assignment.id)).all())
            score = 0.0
            max_score = sum(link.points for link in links)
            correct_count = 0
            needs_review = False
            for link in links:
                question = session.get(QuestionBankItem, link.question_id)
                given = str(answers.get(str(question.id), "")).strip()
                if question.question_type == "short_answer":
                    needs_review = True
                    continue
                is_correct = self._answer_matches(question, given)
                if is_correct:
                    score += link.points
                    correct_count += 1
                else:
                    self._record_mistake(session, student_id, question.id, given)
            submission = AssignmentSubmission(assignment_id=assignment.id, student_id=student_id)
            session.add(submission)
            submission.answers = answers
            submission.score = score
            submission.max_score = max_score
            submission.status = "pending_review" if needs_review else "graded"
            submission.submitted_at = datetime.now().astimezone()
            if late_request is not None:
                late_request.status = "used"
                late_request.used_at = submission.submitted_at
            session.commit()
            session.refresh(submission)
            return {
                "id": str(submission.id), "assignment_id": str(assignment.id), "score": score,
                "max_score": max_score, "correct_count": correct_count, "total_count": len(links),
                "status": submission.status, "submitted_at": submission.submitted_at,
            }

    def update_assignment_status(self, assignment_id: UUID, *, status: str, user_id: UUID, role: str, actor_name: str = "") -> dict | None:
        with self._session_factory() as session:
            assignment = session.scalar(select(Assignment).where(Assignment.id == assignment_id).with_for_update())
            if assignment is None or not self._can_access_assignment(session, assignment, user_id, role):
                return None
            if status == "draft" and assignment.status != "draft":
                raise ValueError("已发布作业不能退回草稿覆盖，请创建独立修订稿；原作答与成绩会保留。")
            if assignment.status == status:
                return self._assignment_dict(session, assignment, user_id=user_id)
            previous_status = assignment.status
            from app.assignment_editor import AssignmentEditorService
            AssignmentEditorService.snapshot(session, user_id, assignment, '状态变更前版本')
            assignment.revision += 1
            assignment.status = status
            session.flush()
            AssignmentEditorService.snapshot(session, user_id, assignment, '教师确认状态变更')
            session.add(AuditLog(actor_id=user_id, actor_name=actor_name,
                action="publish_assignment" if status == "published" else "update_assignment_status",
                resource_type="assignment", resource_id=str(assignment_id),
                detail={"status": status, "previous_status": previous_status, "course_id": str(assignment.course_id),
                        "source_draft_id": str(assignment.source_draft_id) if assignment.source_draft_id else None}))
            session.commit()
            return self._assignment_dict(session, assignment, user_id=user_id)

    def request_late_submission(self, assignment_id: UUID, *, student_id: UUID, reason: str) -> dict:
        with self._session_factory() as session:
            assignment = session.get(Assignment, assignment_id)
            if assignment is None or not self._can_access_assignment(session, assignment, student_id, "student"):
                raise LookupError("作业不存在或不可访问。")
            now = datetime.now(timezone.utc)
            if assignment.due_at is None or now <= self._utc(assignment.due_at):
                raise ValueError("该作业尚未截止，无需申请补交。")
            if session.scalar(select(AssignmentSubmission.id).where(
                AssignmentSubmission.assignment_id == assignment_id, AssignmentSubmission.student_id == student_id
            )) is not None:
                raise ValueError("该作业已经提交，无需申请补交。")
            item = session.scalar(select(LateSubmissionRequest).where(
                LateSubmissionRequest.assignment_id == assignment_id, LateSubmissionRequest.student_id == student_id
            ))
            if item is None:
                item = LateSubmissionRequest(assignment_id=assignment_id, student_id=student_id, reason=reason.strip())
                session.add(item)
            elif item.status == "pending" or (
                item.status == "approved" and (
                    item.approved_until is None or now <= self._utc(item.approved_until)
                )
            ):
                raise ValueError("已有待处理或已批准的补交申请。")
            else:
                item.reason = reason.strip()
                item.status = "pending"
                item.reviewer_id = None
                item.review_note = None
                item.approved_until = None
                item.requested_at = now
                item.reviewed_at = None
                item.used_at = None
            session.commit()
            session.refresh(item)
            return self._late_request_dict(session, item)

    def list_late_submission_requests(self, *, user_id: UUID, role: str, assignment_id: UUID | None = None,
                                      page: int | None = None, page_size: int = 10) -> list[dict] | dict:
        with self._session_factory() as session:
            statement = select(LateSubmissionRequest).join(Assignment, Assignment.id == LateSubmissionRequest.assignment_id).join(
                Course, Course.id == Assignment.course_id
            )
            if role == "student":
                statement = statement.where(LateSubmissionRequest.student_id == user_id)
            elif role == "teacher":
                statement = statement.where(Course.owner_id == user_id)
            if assignment_id:
                statement = statement.where(LateSubmissionRequest.assignment_id == assignment_id)
            statement = statement.order_by(LateSubmissionRequest.requested_at.desc(), LateSubmissionRequest.id.desc())
            if page is not None:
                return sql_page(session, statement, page=page, page_size=page_size,
                                mapper=lambda item: self._late_request_dict(session, item))
            items = list(session.scalars(statement).all())
            return [self._late_request_dict(session, item) for item in items]

    def review_late_submission(self, request_id: UUID, *, reviewer_id: UUID, reviewer_name: str, role: str,
                               status: str, review_note: str | None, approved_until: datetime | None) -> dict | None:
        with self._session_factory() as session:
            item = session.scalar(select(LateSubmissionRequest).where(
                LateSubmissionRequest.id == request_id,
            ).with_for_update())
            if item is None:
                return None
            assignment = session.get(Assignment, item.assignment_id)
            if assignment is None or not self._can_access_assignment(session, assignment, reviewer_id, role):
                return None
            if item.status != "pending":
                raise ValueError("只能审批待处理的补交申请。")
            now = datetime.now(timezone.utc)
            if status == "approved" and approved_until is not None and self._utc(approved_until) <= now:
                raise ValueError("补交截止时间必须晚于当前时间。")
            item.status = status
            item.reviewer_id = reviewer_id
            item.review_note = review_note
            item.approved_until = approved_until if status == "approved" else None
            item.reviewed_at = now
            session.add(AuditLog(
                actor_id=reviewer_id, actor_name=reviewer_name, action=status,
                resource_type="late_submission_request", resource_id=str(request_id),
                detail={"approved_until": approved_until.isoformat() if status == "approved" and approved_until else None},
            ))
            session.commit()
            return self._late_request_dict(session, item)

    def list_submissions(self, assignment_id: UUID, *, user_id: UUID, role: str,
                         page: int | None = None, page_size: int = 10) -> list[dict] | dict | None:
        with self._session_factory() as session:
            assignment = session.get(Assignment, assignment_id)
            if assignment is None or not self._can_access_assignment(session, assignment, user_id, role):
                return None
            statement = select(AssignmentSubmission).where(
                AssignmentSubmission.assignment_id == assignment_id
            ).order_by(AssignmentSubmission.submitted_at.desc(), AssignmentSubmission.id.desc())
            if page is not None:
                return sql_page(session, statement, page=page, page_size=page_size,
                                mapper=lambda item: self._submission_dict(session, item))
            submissions = list(session.scalars(statement).all())
            return [self._submission_dict(session, item) for item in submissions]

    def grade_submission(self, submission_id: UUID, *, teacher_id: UUID, teacher_name: str,
                         role: str, score: float, feedback: str | None,
                         expected_version: str | None = None) -> dict | None:
        with self._session_factory() as session:
            submission = session.scalar(select(AssignmentSubmission).where(
                AssignmentSubmission.id == submission_id,
            ).with_for_update())
            if submission is None:
                return None
            assignment = session.get(Assignment, submission.assignment_id)
            if assignment is None or not self._can_access_assignment(session, assignment, teacher_id, role):
                return None
            if expected_version is not None and self._submission_dict(session, submission)['grading_version'] != expected_version:
                raise SubmissionConflictError('该提交已被其他操作更新。请读取最新成绩并对照当前编辑，再决定是否重新保存。')
            if not math.isfinite(score) or score < 0:
                raise ValueError('成绩必须是有效的非负数。')
            if score > submission.max_score:
                raise ValueError(f"成绩不能超过满分 {submission.max_score:g}。")
            review = session.scalar(select(SubmissionReview).where(SubmissionReview.submission_id == submission_id))
            previous_score = review.score if review else None
            previous_status = submission.status
            if review is None:
                review = SubmissionReview(submission_id=submission_id, teacher_id=teacher_id, score=score, feedback=feedback)
                session.add(review)
            else:
                review.teacher_id = teacher_id
                review.score = score
                review.feedback = feedback
                review.graded_at = datetime.now().astimezone()
            submission.status = "graded"
            session.add(AuditLog(
                actor_id=teacher_id, actor_name=teacher_name, action="grade",
                resource_type="submission", resource_id=str(submission_id),
                detail={"score": score, "previous_score": previous_score,
                        "previous_status": previous_status, "assignment_id": str(submission.assignment_id)},
            ))
            session.commit()
            return self._submission_dict(session, submission)

    def list_wrong_questions(self, *, student_id: UUID, page: int | None = None, page_size: int = 10,
                             course_id:UUID|None=None,keyword:str='',mastery:str='all') -> list[dict] | dict:
        with self._session_factory() as session:
            statement = (
                select(WrongQuestion, QuestionBankItem).join(QuestionBankItem, QuestionBankItem.id == WrongQuestion.question_id)
                .join(CourseEnrollment, CourseEnrollment.course_id == QuestionBankItem.course_id)
                .where(WrongQuestion.student_id == student_id, CourseEnrollment.user_id == student_id,
                       CourseEnrollment.status == "active").order_by(WrongQuestion.updated_at.desc(), WrongQuestion.id.desc())
            )
            def serialize(row):
                wrong, question = row
                return {
                "id": str(wrong.id), "question": self.question_dict(question, reveal_answer=True),
                "wrong_count": wrong.wrong_count, "last_answer": wrong.last_answer,
                "retry_count": wrong.retry_count, "correct_streak": wrong.correct_streak,
                "mastered": wrong.mastered, "last_practiced_at": wrong.last_practiced_at,
                "updated_at": wrong.updated_at,
                }
            if course_id: statement=statement.where(QuestionBankItem.course_id==course_id)
            if mastery == 'pending': statement=statement.where(WrongQuestion.mastered.is_(False))
            elif mastery == 'mastered': statement=statement.where(WrongQuestion.mastered.is_(True))
            elif mastery != 'all': raise ValueError('错题巩固状态无效。')
            if keyword.strip(): statement=statement.where(or_(QuestionBankItem.stem.icontains(keyword.strip(),autoescape=True),QuestionBankItem.knowledge_point.icontains(keyword.strip(),autoescape=True)))
            if page is not None:
                return sql_page(session, statement, page=page, page_size=page_size, mapper=serialize, scalar=False)
            return [serialize(row) for row in session.execute(statement).all()]

    def personalized_practice(self, *, student_id: UUID, course_id: UUID | None, limit: int = 10) -> list[dict]:
        from app.practice_recommendations import PracticeRecommendationService
        return PracticeRecommendationService(self._session_factory).recommend(student_id, course_id, limit)

    def submit_practice_attempt(self, question_id: UUID, *, student_id: UUID, answer: str, request_id: UUID | None = None) -> dict:
        with self._session_factory() as session:
            self._lock_student(session, student_id)
            question = session.get(QuestionBankItem, question_id)
            if question is None or session.scalar(
                select(CourseEnrollment.id).where(
                    CourseEnrollment.user_id == student_id,
                    CourseEnrollment.status == "active",
                    CourseEnrollment.course_id == question.course_id,
                )
            ) is None:
                raise LookupError("题目不存在或当前学生无权练习。")
            answer = answer.strip()
            signature = hashlib.sha256(json.dumps([str(question_id), answer],ensure_ascii=False).encode()).hexdigest()
            if request_id is not None:
                receipt = session.get(PracticeSubmissionReceipt, (student_id, request_id))
                if receipt is not None:
                    if receipt.request_digest != signature:
                        raise ValueError('此提交编号已用于其他作答，请核对上次结果后重新练习。')
                    return dict(receipt.result)
            wrong = session.scalar(select(WrongQuestion).where(
                WrongQuestion.student_id == student_id, WrongQuestion.question_id == question.id
            ))
            source = "wrong_retry" if wrong is not None else "adaptive"
            is_correct = None if question.question_type == "short_answer" else self._answer_matches(question, answer)
            attempt = PracticeAttempt(student_id=student_id, question_id=question.id, answer=answer,
                is_correct=is_correct, source=source, attempted_at=datetime.now(timezone.utc))
            session.add(attempt)
            now = datetime.now().astimezone()
            if wrong is not None:
                wrong.retry_count += 1
                wrong.last_answer = answer
                wrong.last_practiced_at = now
                if is_correct is True:
                    wrong.correct_streak += 1
                    wrong.mastered = wrong.correct_streak >= 2
                elif is_correct is False:
                    self._record_mistake(session, student_id, question.id, answer, wrong)
            elif is_correct is False:
                wrong = self._record_mistake(session, student_id, question.id, answer)
                wrong.retry_count = 1
                wrong.last_practiced_at = now
            session.flush()
            result = {
                "attempt_id": str(attempt.id), "question_id": str(question.id), "is_correct": is_correct,
                "needs_review": is_correct is None,
                "correct_answer": question.correct_answer if is_correct is not None else None,
                "explanation": question.explanation,
                "correct_streak": wrong.correct_streak if wrong else 0,
                "mastered": wrong.mastered if wrong else bool(is_correct),
                "message": "主观题已记录，请结合解析自评。" if is_correct is None else
                    ("回答正确；再独立答对一次后标记本题已巩固。" if wrong and not wrong.mastered and is_correct else
                     "回答正确，本题已巩固。" if is_correct and wrong else "本次回答正确。" if is_correct else "回答不正确，已加入待巩固错题。"),
            }
            if request_id is not None:
                session.add(PracticeSubmissionReceipt(student_id=student_id,request_id=request_id,attempt_id=attempt.id,
                    request_digest=signature,result=result))
            session.commit()
            return result

    @classmethod
    def _practice_item(cls, question: QuestionBankItem, *, priority: int, reason: str, source: str, retry_count: int) -> dict:
        return {"question": cls.question_dict(question, reveal_answer=False), "priority": priority,
                "reason": reason, "source": source, "retry_count": retry_count}

    def mark_mastered(self, wrong_id: UUID, *, student_id: UUID) -> bool:
        with self._session_factory() as session:
            self._lock_student(session, student_id)
            wrong = session.scalar(select(WrongQuestion).where(WrongQuestion.id == wrong_id, WrongQuestion.student_id == student_id))
            if wrong is None:
                return False
            question = session.get(QuestionBankItem, wrong.question_id)
            if question is None or session.scalar(select(CourseEnrollment.id).where(
                CourseEnrollment.course_id == question.course_id, CourseEnrollment.user_id == student_id,
                CourseEnrollment.status == "active")) is None:
                return False
            if not wrong.mastered:
                raise ValueError('请通过独立练习巩固本题，不能手动改变巩固状态。')
            wrong.mastered = True
            session.commit()
            return True

    def _assignment_dicts(self,session,assignments,user_id):
        if not assignments:return []
        ids=[a.id for a in assignments]
        titles=dict(session.execute(select(Course.id,Course.title).where(Course.id.in_({a.course_id for a in assignments}))).all())
        questions=dict(session.execute(select(AssignmentQuestion.assignment_id,func.count()).where(AssignmentQuestion.assignment_id.in_(ids)).group_by(AssignmentQuestion.assignment_id)).all())
        counts={row[0]:(int(row[1]),int(row[2])) for row in session.execute(select(AssignmentSubmission.assignment_id,func.count(),func.sum(case((AssignmentSubmission.status!='graded',1),else_=0))).where(AssignmentSubmission.assignment_id.in_(ids)).group_by(AssignmentSubmission.assignment_id))}
        submissions={row.assignment_id:row for row in session.scalars(select(AssignmentSubmission).where(AssignmentSubmission.assignment_id.in_(ids),AssignmentSubmission.student_id==user_id))}
        reviews={row.submission_id:row for row in session.scalars(select(SubmissionReview).where(SubmissionReview.submission_id.in_([r.id for r in submissions.values()])))}
        late={row.assignment_id:row for row in session.scalars(select(LateSubmissionRequest).where(LateSubmissionRequest.assignment_id.in_(ids),LateSubmissionRequest.student_id==user_id))}
        cache=(titles,questions,counts,submissions,reviews,late)
        return [self._assignment_dict(session,a,user_id=user_id,preloaded=cache) for a in assignments]

    def _assignment_dict(self, session, assignment: Assignment, *, user_id: UUID, preloaded=None) -> dict:
        if preloaded is not None:
            titles,questions,counts,submissions,reviews,late=preloaded
            course_title=titles.get(assignment.course_id,'课程')
            question_count=questions.get(assignment.id,0)
            submission_count,ungraded_count=counts.get(assignment.id,(0,0))
            submission=submissions.get(assignment.id)
            review=reviews.get(submission.id) if submission else None
            late_request=late.get(assignment.id)
        else:
            return self._single_assignment_dict(session,assignment,user_id=user_id)
        return self._assignment_values(assignment,course_title,question_count,submission_count,ungraded_count,submission,review,late_request)

    def _single_assignment_dict(self, session, assignment: Assignment, *, user_id: UUID) -> dict:
        course = session.get(Course, assignment.course_id)
        course_title = course.title if course else "课程"
        question_count = int(session.scalar(select(func.count(AssignmentQuestion.id)).where(AssignmentQuestion.assignment_id == assignment.id)) or 0)
        submission_count = int(session.scalar(select(func.count(AssignmentSubmission.id)).where(AssignmentSubmission.assignment_id == assignment.id)) or 0)
        submission = session.scalar(select(AssignmentSubmission).where(AssignmentSubmission.assignment_id == assignment.id, AssignmentSubmission.student_id == user_id))
        review = session.scalar(select(SubmissionReview).where(SubmissionReview.submission_id == submission.id)) if submission else None
        late_request = session.scalar(select(LateSubmissionRequest).where(
            LateSubmissionRequest.assignment_id == assignment.id, LateSubmissionRequest.student_id == user_id
        ))
        ungraded_count=int(session.scalar(select(func.count(AssignmentSubmission.id)).where(AssignmentSubmission.assignment_id==assignment.id,AssignmentSubmission.status!='graded')) or 0)
        return self._assignment_values(assignment,course_title,question_count,submission_count,ungraded_count,submission,review,late_request)

    @staticmethod
    def _assignment_values(assignment,course_title,question_count,submission_count,ungraded_count,submission,review,late_request):
        return {
            "id": str(assignment.id), "course_id": str(assignment.course_id),
            "class_id": str(assignment.class_id) if assignment.class_id else None, "course_title": course_title,
            "source_draft_id": str(assignment.source_draft_id) if assignment.source_draft_id else None,
            "revision": assignment.revision, "ai_policy": assignment.ai_policy,
            "previous_version_id": str(assignment.previous_version_id) if assignment.previous_version_id else None,
            "title": assignment.title, "description": assignment.description, "status": assignment.status,
            "due_at": assignment.due_at, "question_count": question_count, "submission_count": submission_count,
            "ungraded_count": ungraded_count,
            "submitted": submission is not None,
            "submission_status": submission.status if submission else None,
            "submitted_answers": submission.answers if submission else None,
            "score": (review.score if review else submission.score) if submission and submission.status == "graded" else None,
            "max_score": submission.max_score if submission else None, "created_at": assignment.created_at,
            "teacher_feedback": review.feedback if review and submission.status == "graded" else None,
            "late_request_status": late_request.status if late_request else None,
            "late_approved_until": late_request.approved_until if late_request else None,
        }

    def _late_request_dict(self, session, item: LateSubmissionRequest) -> dict:
        assignment = session.get(Assignment, item.assignment_id)
        student = session.get(User, item.student_id)
        reviewer = session.get(User, item.reviewer_id) if item.reviewer_id else None
        return {
            "id": str(item.id), "assignment_id": str(item.assignment_id),
            "assignment_title": assignment.title if assignment else "作业",
            "student_id": str(item.student_id), "student_name": student.display_name if student else "学生",
            "reason": item.reason, "status": item.status, "reviewer_name": reviewer.display_name if reviewer else None,
            "review_note": item.review_note, "approved_until": item.approved_until,
            "requested_at": item.requested_at, "reviewed_at": item.reviewed_at, "used_at": item.used_at,
        }

    def _submission_dict(self, session, submission: AssignmentSubmission) -> dict:
        student = session.get(User, submission.student_id)
        review = session.scalar(select(SubmissionReview).where(SubmissionReview.submission_id == submission.id))
        result = {
            "id": str(submission.id), "assignment_id": str(submission.assignment_id),
            "student_id": str(submission.student_id), "student_name": student.display_name if student else "学生",
            "answers": submission.answers, "score": review.score if review else submission.score,
            "max_score": submission.max_score, "status": submission.status,
            "feedback": review.feedback if review else None, "submitted_at": submission.submitted_at,
            "graded_at": review.graded_at if review else None,
        }
        version_fields = {key: value for key, value in result.items() if key != 'student_name'}
        result['grading_version'] = hashlib.sha256(json.dumps(
            version_fields, sort_keys=True, ensure_ascii=False, default=str,
        ).encode('utf-8')).hexdigest()
        return result

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(value.lower().split()).replace("。", "").replace("，", ",")

    @classmethod
    def _answer_matches(cls, question: QuestionBankItem, given: str) -> bool:
        if question.question_type == "multiple_choice":
            expected = {cls._choice_key(question, value) for value in cls._split_multiple(question.correct_answer)}
            actual = {cls._choice_key(question, value) for value in cls._split_multiple(given)}
            return bool(expected) and expected == actual
        if question.question_type in {"single_choice", "true_false"} and question.options:
            return cls._choice_key(question, given) == cls._choice_key(question, question.correct_answer)
        if question.question_type == "fill_blank":
            expected_blanks = cls._split_blanks(question.correct_answer)
            actual_blanks = cls._split_blanks(given)
            if len(expected_blanks) != len(actual_blanks):
                return False
            for expected, actual in zip(expected_blanks, actual_blanks, strict=True):
                alternatives = {cls._normalize(value) for value in re.split(r"[/／]", expected) if value.strip()}
                if cls._normalize(actual) not in alternatives:
                    return False
            return True
        return cls._normalize(given) == cls._normalize(question.correct_answer)

    @classmethod
    def _choice_key(cls, question: QuestionBankItem, value: str) -> str:
        normalized = cls._normalize(value)
        for index, option in enumerate(question.options or []):
            label = re.match(r"^([A-J])\s*[.、:：)）]\s*(.+)$", option.strip(), flags=re.IGNORECASE)
            variants = {cls._normalize(option), chr(ord("a") + index)}
            if label:
                variants.add(cls._normalize(label.group(2)))
                variants.add(label.group(1).lower())
            if normalized in variants:
                return f"option:{index}"
        return f"raw:{normalized}"

    @staticmethod
    def _split_multiple(value: str) -> list[str]:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
        return [item.strip() for item in re.split(r"[,，;；|、\n]+", value) if item.strip()]

    @staticmethod
    def _split_blanks(value: str) -> list[str]:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return [item.strip() for item in value.split("||")]

    @staticmethod
    def _can_access_assignment(session, assignment: Assignment, user_id: UUID, role: str) -> bool:
        if role == "admin":
            return True
        course = session.get(Course, assignment.course_id)
        if role == "teacher":
            return course is not None and course.owner_id == user_id
        if assignment.status not in {"published", "closed"}:
            return False
        return session.scalar(select(CourseEnrollment.id).where(
            CourseEnrollment.course_id == assignment.course_id, CourseEnrollment.user_id == user_id,
            CourseEnrollment.status == "active")) is not None
