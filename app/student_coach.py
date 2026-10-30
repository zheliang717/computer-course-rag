"""Personal study navigation from verified records, without exposing answer keys."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, case, func, select

from app.models import (
    Assignment, AssignmentSubmission, Course, CourseEnrollment, CourseSession,
    QuestionBankItem, WrongQuestion,
)


class StudentCoachService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def answer(self, *, user_id: UUID, question: str, course_id: UUID | None = None) -> dict | None:
        compact = re.sub(r"\s+", "", question)
        wants_weakness = bool(re.search(r"薄弱|弱项|错题.*(?:分析|复习|巩固)|(?:分析|复习|巩固).*错题", compact))
        wants_plan = bool(re.search(r"学习计划|复习计划|学习安排|复习安排|学习建议|"
                                   r"(?:安排|规划).*?(?:学习|复习)|(?:学习|复习).*?(?:安排|规划)|先学什么|先复习什么", compact))
        if not wants_weakness and not wants_plan:
            return None
        now = datetime.now(timezone.utc)
        local_zone = timezone(timedelta(hours=8))
        with self._session_factory() as session:
            courses = dict(session.execute(select(Course.id, Course.title).join(
                CourseEnrollment, CourseEnrollment.course_id == Course.id,
            ).where(CourseEnrollment.user_id == user_id, CourseEnrollment.status == "active",
                    Course.status == "published").order_by(Course.title, Course.id)).all())
            if course_id is not None and course_id not in courses:
                raise PermissionError("课程不存在或当前学生未加入。")
            scope = ([course_id] if course_id is not None and not re.search(r"全部课程|所有课程|各门课", compact)
                     else list(courses))
            if not scope:
                return {"answer": "### 学习建议\n\n当前还没有可访问的课程。加入课程后，我可以结合你的作业和练习记录整理下一步。", "actions": []}

            wrong_filter = (WrongQuestion.student_id == user_id, WrongQuestion.mastered.is_(False),
                            QuestionBankItem.course_id.in_(scope))
            weak_points = session.execute(select(
                QuestionBankItem.course_id, QuestionBankItem.knowledge_point,
                func.count(WrongQuestion.id).label("question_count"),
                func.sum(WrongQuestion.wrong_count).label("mistakes"),
            ).join(QuestionBankItem, QuestionBankItem.id == WrongQuestion.question_id)
                .where(*wrong_filter).group_by(QuestionBankItem.course_id, QuestionBankItem.knowledge_point)
                .order_by(func.sum(WrongQuestion.wrong_count).desc(), func.count(WrongQuestion.id).desc(),
                          QuestionBankItem.course_id, QuestionBankItem.knowledge_point).limit(4)).all()
            # Select only identifiers and learning metadata: never correct_answer/explanation/last_answer.
            retry_questions = session.execute(select(
                QuestionBankItem.id, QuestionBankItem.course_id, QuestionBankItem.knowledge_point,
                WrongQuestion.wrong_count,
            ).join(QuestionBankItem, QuestionBankItem.id == WrongQuestion.question_id)
                .where(*wrong_filter).order_by(WrongQuestion.wrong_count.desc(), WrongQuestion.updated_at.desc(),
                                             WrongQuestion.id).limit(3)).all()
            pending = list(session.scalars(select(Assignment).outerjoin(AssignmentSubmission, and_(
                AssignmentSubmission.assignment_id == Assignment.id, AssignmentSubmission.student_id == user_id,
            )).where(Assignment.course_id.in_(scope), Assignment.status == "published", AssignmentSubmission.id.is_(None))
                .order_by(case((Assignment.due_at < now, 1), else_=0), Assignment.due_at.asc().nulls_last(), Assignment.id)
                .limit(3)).all())

            heading = f"{courses[scope[0]]} · " if len(scope) == 1 else ""
            lines = [f"### {heading}{'薄弱点与复习建议' if wants_weakness else '下一步学习安排'}", "",
                     "根据你当前可访问的课程与学习记录整理。先处理临近截止的任务，再集中巩固少量错题。"]
            actions: list[dict[str, str]] = []
            if pending and wants_plan:
                lines.extend(["", "#### 先处理待交任务"])
                for item in pending:
                    due = item.due_at.astimezone(local_zone) if item.due_at else None
                    deadline = ("已逾期，先查看补交申请" if item.due_at and item.due_at < now else
                                f"截止 {due:%m月%d日 %H:%M}" if due else "未设截止时间")
                    lines.append(f"- **{courses[item.course_id]} · {item.title}**：{deadline}。")
                    actions.append({"kind": "assignment", "target_id": str(item.id), "title": item.title,
                                    "detail": f"{courses[item.course_id]} · {deadline}"})
            if weak_points:
                lines.extend(["", "#### 值得优先巩固的知识点"])
                for point in weak_points:
                    topic = point.knowledge_point or "未标注知识点"
                    lines.append(f"- **{courses[point.course_id]} · {topic}**：{point.question_count} 道待掌握题，"
                                 f"累计 {point.mistakes} 次错误。先独立重做，再对照解析复盘。")
                lines.append("\n这些是已记录错题反映的线索，不代表完整的能力评价；练习量不足时不能据此下结论。")
                for item in retry_questions:
                    actions.append({"kind": "wrong_question", "target_id": str(item.id),
                                    "title": f"重练：{item.knowledge_point or '课程错题'}",
                                    "detail": f"{courses[item.course_id]} · 已记录 {item.wrong_count} 次错误"})
            else:
                lines.extend(["", "当前没有记录到尚未掌握的错题。可以先完成课程练习，再根据结果调整复习重点；这不等于所有知识点均已掌握。"])
            if wants_plan:
                upcoming = session.scalar(select(CourseSession).where(
                    CourseSession.course_id.in_(scope), CourseSession.completed.is_(False),
                    CourseSession.session_date >= now,
                ).order_by(CourseSession.session_date, CourseSession.id).limit(1))
                if upcoming:
                    when = upcoming.session_date.astimezone(local_zone)
                    lines.extend(["", "#### 留一点时间预习", f"下一课次：**{courses[upcoming.course_id]} · {upcoming.title}**，"
                                  f"{when:%m月%d日 %H:%M}。可打开课程大纲和对应资料预习。"])
                    actions.append({"kind": "course", "target_id": str(upcoming.course_id),
                                    "title": f"预习：{upcoming.title}", "detail": courses[upcoming.course_id]})
                plan_course = scope[0] if len(scope) == 1 else (pending[0].course_id if pending else
                              retry_questions[0].course_id if retry_questions else scope[0])
                actions.append({"kind": "study_plan", "target_id": str(plan_course),
                                "title": f"打开{courses[plan_course]}学习计划", "detail": "查看已有计划，或自行确认创建新计划"})
            return {"answer": "\n".join(lines), "actions": actions, "source_course_ids": [str(item) for item in scope]}
