"""Teacher navigation and anonymous learning snapshots, computed from course records."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import case, func, select

from app.models import (
    Assignment, AssignmentSubmission, Course, CourseEnrollment, PracticeAttempt,
    QuestionBankItem, TeachingDraft, WrongQuestion,
)


class TeacherCoachService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _managed_course(session, course_id, actor_id, role):
        course = session.get(Course, course_id)
        return course if course and (role == "admin" or role == "teacher" and course.owner_id == actor_id) else None

    @staticmethod
    def _cohort(course_id):
        return select(CourseEnrollment.user_id).where(
            CourseEnrollment.course_id == course_id, CourseEnrollment.status == "active")

    @classmethod
    def _point(cls, session, course_id, topic, now):
        cohort = cls._cohort(course_id)
        conditions = [QuestionBankItem.course_id == course_id, WrongQuestion.student_id.in_(cohort),
                      WrongQuestion.mastered.is_(False)]
        if topic is not None:
            conditions.append(QuestionBankItem.knowledge_point == topic)
        learners, questions, mistakes = session.execute(select(
            func.count(func.distinct(WrongQuestion.student_id)), func.count(WrongQuestion.id),
            func.coalesce(func.sum(WrongQuestion.wrong_count), 0),
        ).join(QuestionBankItem, QuestionBankItem.id == WrongQuestion.question_id).where(*conditions)).one()
        practice = cls._practice(session, course_id, topic, now - timedelta(days=14), now)
        return {"topic": topic, "unresolved_students": int(learners), "unresolved_questions": int(questions),
                "recorded_mistakes": int(mistakes), "practice": practice}

    @classmethod
    def _practice(cls, session, course_id, topic, start, end, question_ids=None):
        conditions = [QuestionBankItem.course_id == course_id,
                      PracticeAttempt.student_id.in_(cls._cohort(course_id)),
                      PracticeAttempt.attempted_at >= start, PracticeAttempt.attempted_at <= end]
        if topic is not None and question_ids is None:
            conditions.append(QuestionBankItem.knowledge_point == topic)
        if question_ids is not None:
            conditions.append(QuestionBankItem.id.in_(question_ids))
        attempts, learners, scored, correct = session.execute(select(
            func.count(PracticeAttempt.id), func.count(func.distinct(PracticeAttempt.student_id)),
            func.count(PracticeAttempt.is_correct),
            func.coalesce(func.sum(case((PracticeAttempt.is_correct.is_(True), 1), else_=0)), 0),
        ).join(QuestionBankItem, QuestionBankItem.id == PracticeAttempt.question_id).where(*conditions)).one()
        return {"attempts": int(attempts), "students": int(learners), "scored_attempts": int(scored),
                "correct_attempts": int(correct), "accuracy_percent": round(correct / scored * 100, 1) if scored else None}

    def insights(self, course_id: UUID, *, actor_id: UUID, role: str, focus: str | None = None) -> dict | None:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            course = self._managed_course(session, course_id, actor_id, role)
            if course is None:
                return None
            cohort = self._cohort(course_id)
            students = session.scalar(select(func.count(CourseEnrollment.id)).where(
                CourseEnrollment.course_id == course_id, CourseEnrollment.status == "active")) or 0
            rows = session.execute(select(
                QuestionBankItem.knowledge_point,
                func.count(func.distinct(WrongQuestion.student_id)).label("learners"),
                func.count(WrongQuestion.id).label("questions"),
                func.sum(WrongQuestion.wrong_count).label("mistakes"),
            ).join(QuestionBankItem, QuestionBankItem.id == WrongQuestion.question_id).where(
                QuestionBankItem.course_id == course_id, WrongQuestion.student_id.in_(cohort),
                WrongQuestion.mastered.is_(False), QuestionBankItem.knowledge_point.is_not(None),
                func.length(func.trim(QuestionBankItem.knowledge_point)) > 0,
            ).group_by(QuestionBankItem.knowledge_point).order_by(
                func.count(func.distinct(WrongQuestion.student_id)).desc(),
                func.sum(WrongQuestion.wrong_count).desc(), QuestionBankItem.knowledge_point).limit(5)).all()
            weak = [{"topic": row.knowledge_point, "unresolved_students": int(row.learners),
                     "unresolved_questions": int(row.questions), "recorded_mistakes": int(row.mistakes)} for row in rows]
            if focus and session.scalar(select(QuestionBankItem.id).where(
                QuestionBankItem.course_id == course_id, QuestionBankItem.knowledge_point == focus).limit(1)) is None:
                raise ValueError("该知识点已不属于当前课程题库，请刷新学情后重新选择。")
            assignment_count = session.scalar(select(func.count(Assignment.id)).where(
                Assignment.course_id == course_id, Assignment.status.in_(("published", "closed")))) or 0
            pending_reviews = session.scalar(select(func.count(AssignmentSubmission.id)).join(
                Assignment, Assignment.id == AssignmentSubmission.assignment_id).where(
                Assignment.course_id == course_id, Assignment.status.in_(("published", "closed")),
                AssignmentSubmission.student_id.in_(cohort), AssignmentSubmission.status != "graded")) or 0
            submitted = select(func.count(AssignmentSubmission.id)).where(
                AssignmentSubmission.assignment_id == Assignment.id,
                AssignmentSubmission.student_id.in_(cohort)).correlate(Assignment).scalar_subquery()
            pending = select(func.count(AssignmentSubmission.id)).where(
                AssignmentSubmission.assignment_id == Assignment.id,
                AssignmentSubmission.student_id.in_(cohort), AssignmentSubmission.status != "graded",
            ).correlate(Assignment).scalar_subquery()
            assignments = session.execute(select(Assignment, submitted.label("submitted"), pending.label("pending"))
                .where(Assignment.course_id == course_id, Assignment.status.in_(("published", "closed")), submitted > 0)
                .order_by(Assignment.created_at.desc(), Assignment.id.desc()).limit(5)).all()
            return {"course_id": str(course_id), "course_title": course.title, "generated_at": now.isoformat(),
                    "student_count": int(students), "assignment_count": int(assignment_count),
                    "pending_review_count": int(pending_reviews), "weak_points": weak,
                    "focus": self._point(session, course_id, focus, now) if focus else None,
                    "assignments": [{"id": str(item.id), "title": item.title, "submission_count": int(total),
                                     "pending_review_count": int(waiting),
                                     "has_published_review": item.published_review_draft_id is not None}
                                    for item, total, waiting in assignments]}

    def answer(self, *, actor_id: UUID, role: str, question: str, course_id: UUID | None) -> dict | None:
        if not re.search(r"学情|薄弱|教学建议|备课|教学计划|教案|(?:练习题|题目)草稿|补充练习|作业讲评", question):
            return None
        if course_id is None:
            return {"answer": "请先在助手中选择一门教学课程。我会核对课程学习记录，再帮你准备备课、练习或讲评草稿。", "actions": []}
        snapshot = self.insights(course_id, actor_id=actor_id, role=role)
        if snapshot is None:
            raise PermissionError("课程不存在或当前用户无权管理。")
        lines = [f"### {snapshot['course_title']} · 教学建议", "",
                 f"当前有 {snapshot['student_count']} 位在课学生、{snapshot['assignment_count']} 份已发布或关闭的作业，"
                 f"{snapshot['pending_review_count']} 份提交待批改。", "", "#### 可以优先处理"]
        actions = [{"kind": "course_analysis", "target_id": str(course_id),
                    "title": "全体成绩与 AI 综合分析", "detail": "查看成绩分布、实名学生与教学建议"}]
        for point in snapshot["weak_points"][:3]:
            lines.append(f"- **{point['topic']}**：{point['unresolved_students']} 位学生仍有未掌握记录，"
                         f"涉及 {point['unresolved_questions']} 条错题记录。建议先做短讲解，再安排针对性练习。")
        if not snapshot["weak_points"]:
            lines.append("- 当前没有已标注知识点的未掌握错题记录；不能因此认定所有学生都已掌握，可准备诊断练习。")
        topic = snapshot["weak_points"][0]["topic"] if snapshot["weak_points"] else None
        for kind, title in (("teacher_plan", "准备针对性教案"), ("teacher_questions", "准备补充练习草稿")):
            actions.append({"kind": kind, "target_id": str(course_id), "topic": topic,
                            "title": f"{topic} · {title}" if topic else title, "detail": "先选择生成设置，草稿需教师审核"})
        for item in snapshot["assignments"][:2]:
            actions.append({"kind": "assignment", "target_id": item["id"], "title": f"讲评：{item['title']}",
                            "detail": f"{item['submission_count']} 份提交 · {item['pending_review_count']} 份待批改"})
        lines.extend(["", "以上来自平台记录，不是模型推测。错题样本只是教学线索；草稿、讲评和题目都需你核对确认。"])
        return {"answer": "\n".join(lines), "actions": actions, "source_course_ids": [str(course_id)]}

    @staticmethod
    def local_outline(snapshot: dict, topic: str) -> str:
        """Editable planning scaffold, not a generated explanation or invented question set."""
        focus = snapshot.get("focus")
        observation = (f"{focus['unresolved_students']} 位学生有 {focus['unresolved_questions']} 条未掌握错题记录。"
                       if focus else "尚未指定单一知识点，请教师结合具体章节补充教学重点。")
        return (f"## {snapshot['course_title']} · {topic}\n\n"
                "> 站内记录提纲：未调用在线模型，不含教材讲解或自动生成的参考答案。\n\n"
                f"### 教学观察\n\n- 在课学生：{snapshot['student_count']} 人\n"
                f"- 待批改提交：{snapshot['pending_review_count']} 份\n- {observation}\n\n"
                "### 教学目标（请补充）\n\n- 本次需要理解的概念：\n- 需要独立完成的操作或推导：\n\n"
                "### 建议课堂安排（可修改）\n\n"
                "| 环节 | 建议时长 | 教师待准备内容 |\n| --- | --- | --- |\n"
                "| 诊断回顾 | 5 分钟 | 选取已有错题，不提前展示答案 |\n"
                "| 概念梳理 | 10 分钟 | 核对课程资料，补充关键概念 |\n"
                "| 示例分析 | 15 分钟 | 准备正例与易错对比 |\n"
                "| 独立练习 | 10 分钟 | 从题库选择或审核补充题目 |\n"
                "| 课堂检查 | 5 分钟 | 收集学生解释，记录仍待澄清的问题 |\n\n"
                "### 课后跟进\n\n- 核对未批改作业后准备讲评。\n"
                "- 练习完成后回看本知识点记录；不能把样本变化直接解释为教学效果。\n"
                "- 本提纲仅保存草稿，不代表已授课或已布置作业。")

    def impact(self, draft_id: UUID, *, actor_id: UUID, role: str) -> dict | None:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            draft = session.get(TeachingDraft, draft_id)
            if draft is None or (role != "admin" and draft.creator_id != actor_id) or not self._managed_course(
                session, draft.course_id, actor_id, role):
                return None
            context = draft.source_context or {}
            snapshot = context.get("teaching_snapshot")
            topic = context.get("focus_knowledge_point")
            if not isinstance(snapshot, dict):
                raise ValueError("这份草稿没有记录生成时的学情快照，无法做前后回看。")
            raw_published = context.get("published_at") if draft.status == "published" else None
            published_at = datetime.fromisoformat(raw_published) if raw_published else None
            question_ids = [UUID(value) for value in context.get("published_question_ids", [])]
            # A confirmed lesson plan is not a delivered lesson; only explicit question publication starts this window.
            after = self._practice(session, draft.course_id, topic, published_at, now, question_ids) if (
                published_at and question_ids) else None
            current = self._point(session, draft.course_id, topic, now) if topic else None
            students = session.scalar(select(func.count(CourseEnrollment.id)).where(
                CourseEnrollment.course_id == draft.course_id, CourseEnrollment.status == "active")) or 0
            return {"draft_id": str(draft.id), "course_id": str(draft.course_id), "topic": topic,
                    "generated_at": now.isoformat(), "baseline": snapshot, "current_focus": current,
                    "current_student_count": int(students), "published_at": raw_published,
                    "published_question_count": len(question_ids), "published_question_practice": after,
                    "note": "生成时快照与当前数据用于回看；练习窗口、参与学生和题库可能变化，不能据此证明教学效果或因果提升。未评分主观题不计入正确率。"}
