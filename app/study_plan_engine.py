"""Immutable arrangements, live activity feedback, and explicit record-driven replanning."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import load_only

from app.models import (Assignment, AssignmentQuestion, AssignmentSubmission, AuditLog, Course, CourseEnrollment,
    CourseSection, CourseSession, LateSubmissionRequest, PracticeAttempt, QuestionBankItem, StudyPlan, User, WrongQuestion)
from app.pagination import sql_page
from app.schemas import StudyPlanPreferences


def utc(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def identifier(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def iso(value):
    return utc(value).isoformat() if value else None


class StudyPlanService:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @staticmethod
    def _course(session, student_id, course_id, *, lock=False):
        query = select(CourseEnrollment).join(Course, Course.id == CourseEnrollment.course_id).where(
            CourseEnrollment.user_id == student_id, CourseEnrollment.course_id == course_id,
            CourseEnrollment.status == "active", Course.status == "published")
        enrollment = session.scalar(query.with_for_update(of=CourseEnrollment) if lock else query)
        if enrollment is None:
            raise LookupError("课程不存在、已下架或当前学生未加入课程。")
        return session.get(Course, course_id)

    @classmethod
    def _plan(cls, session, student_id, plan_id):
        plan = session.scalar(select(StudyPlan).where(StudyPlan.id == plan_id, StudyPlan.student_id == student_id))
        if plan is None:
            raise LookupError("学习安排不存在或无权查看。")
        return plan, cls._course(session, student_id, plan.course_id)

    @staticmethod
    def _latest(session, student_id, course_id):
        return session.scalar(select(StudyPlan).where(StudyPlan.student_id == student_id, StudyPlan.course_id == course_id)
            .order_by(StudyPlan.revision.desc(), StudyPlan.created_at.desc(), StudyPlan.id.desc()).limit(1))

    @staticmethod
    def _context(session, student_id, course_ids):
        """Batch metadata for every requested course; never load answers or answer keys."""
        data = {key: {} for key in ("assignments", "submissions", "questions", "wrong", "late")}
        data.update(attempts=defaultdict(list), sections=defaultdict(list), sessions=defaultdict(list),
            links=defaultdict(list), now=datetime.now(timezone.utc))
        for row in session.scalars(select(Assignment).where(Assignment.course_id.in_(course_ids),
            Assignment.status.in_(("published", "closed"))).options(load_only(
            Assignment.id, Assignment.course_id, Assignment.title, Assignment.status, Assignment.due_at))):
            data["assignments"][row.id] = row
        assignment_ids = list(data["assignments"])
        if assignment_ids:
            for row in session.scalars(select(AssignmentSubmission).where(AssignmentSubmission.student_id == student_id,
                AssignmentSubmission.assignment_id.in_(assignment_ids)).options(load_only(AssignmentSubmission.id,
                AssignmentSubmission.assignment_id, AssignmentSubmission.status, AssignmentSubmission.score,
                AssignmentSubmission.max_score, AssignmentSubmission.submitted_at))):
                data["submissions"][row.assignment_id] = row
            for row in session.scalars(select(LateSubmissionRequest).where(LateSubmissionRequest.student_id == student_id,
                LateSubmissionRequest.assignment_id.in_(assignment_ids)).options(load_only(LateSubmissionRequest.id,
                LateSubmissionRequest.assignment_id, LateSubmissionRequest.status, LateSubmissionRequest.approved_until,
                LateSubmissionRequest.used_at))):
                data["late"][row.assignment_id] = row
            for assignment_id, question_id in session.execute(select(AssignmentQuestion.assignment_id,
                AssignmentQuestion.question_id).where(AssignmentQuestion.assignment_id.in_(assignment_ids))):
                data["links"][assignment_id].append(question_id)
        for row in session.scalars(select(QuestionBankItem).where(QuestionBankItem.course_id.in_(course_ids)).options(load_only(
            QuestionBankItem.id, QuestionBankItem.course_id, QuestionBankItem.question_type, QuestionBankItem.knowledge_point,
            QuestionBankItem.stem, QuestionBankItem.difficulty))):
            data["questions"][row.id] = row
        question_ids = list(data["questions"])
        if question_ids:
            for row in session.scalars(select(WrongQuestion).where(WrongQuestion.student_id == student_id,
                WrongQuestion.question_id.in_(question_ids)).options(load_only(WrongQuestion.id, WrongQuestion.question_id,
                WrongQuestion.wrong_count, WrongQuestion.mastered, WrongQuestion.correct_streak, WrongQuestion.updated_at))):
                data["wrong"][row.question_id] = row
            for row in session.execute(select(PracticeAttempt.id, PracticeAttempt.question_id, PracticeAttempt.is_correct,
                PracticeAttempt.attempted_at).where(PracticeAttempt.student_id == student_id, PracticeAttempt.question_id.in_(question_ids))
                .order_by(PracticeAttempt.attempted_at, PracticeAttempt.id)):
                data["attempts"][row.question_id].append(row)
        for row in session.scalars(select(CourseSection).where(CourseSection.course_id.in_(course_ids), CourseSection.archived.is_(False))
            .options(load_only(CourseSection.id, CourseSection.course_id, CourseSection.title, CourseSection.position))
            .order_by(CourseSection.position, CourseSection.id)):
            data["sections"][row.course_id].append(row)
        for row in session.scalars(select(CourseSession).where(CourseSession.course_id.in_(course_ids)).options(load_only(
            CourseSession.id, CourseSession.course_id, CourseSession.section_id, CourseSession.completed, CourseSession.session_date))):
            data["sessions"][row.course_id].append(row)
        return data

    @staticmethod
    def _assignment_hint(assignment, context):
        if assignment.status == "closed":
            return "作业已关闭"
        if assignment.due_at and utc(assignment.due_at) < context["now"]:
            late = context["late"].get(assignment.id)
            if late and late.status == "approved" and late.approved_until and not late.used_at and utc(late.approved_until) > context["now"]:
                return "补交已获批准，可打开作业继续完成"
            if late and late.status == "pending":
                return "已申请补交，等待教师处理"
            return "已逾期，可打开作业查看补交方式"
        when = utc(assignment.due_at).astimezone(timezone(timedelta(hours=8))) if assignment.due_at else None
        return f"截止 {when:%m月%d日 %H:%M}" if when else "未设截止时间"

    @staticmethod
    def _blocked(context):
        result = {}
        for assignment in context["assignments"].values():
            if assignment.status == "published" and assignment.id not in context["submissions"]:
                for question_id in context["links"].get(assignment.id, []):
                    result.setdefault(question_id, assignment.id)
        return result

    @classmethod
    def _signature(cls, course, context):
        assignments = [row for row in context["assignments"].values() if row.course_id == course.id]
        questions = [row for row in context["questions"].values() if row.course_id == course.id]
        records = {"format": 2, "course": str(course.id), "assignments": [], "questions": [], "schedule": []}
        for row in sorted(assignments, key=lambda x: str(x.id)):
            submission = context["submissions"].get(row.id)
            records["assignments"].append([str(row.id), row.title, row.status, iso(row.due_at), cls._assignment_hint(row, context),
                [str(q) for q in sorted(context["links"].get(row.id, []), key=str)],
                [str(submission.id), submission.status, submission.score, submission.max_score] if submission else None])
        for row in sorted(questions, key=lambda x: str(x.id)):
            wrong = context["wrong"].get(row.id)
            records["questions"].append([str(row.id), row.stem, row.question_type, row.knowledge_point, row.difficulty,
                [wrong.wrong_count, wrong.mastered, wrong.correct_streak] if wrong else None,
                [[str(a.id), a.is_correct, iso(a.attempted_at)] for a in context["attempts"].get(row.id, [])]])
        records["schedule"] = [[str(row.id), row.title, row.position] for row in context["sections"][course.id]] + [
            [str(row.id), str(row.section_id), row.completed, iso(row.session_date)]
            for row in sorted(context["sessions"][course.id], key=lambda x: str(x.id))]
        return hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    @classmethod
    def _render_item(cls, plan, raw, context):
        kind = raw.get("kind", "course_review")
        target = identifier(raw.get("target_id"))
        result = {**raw, "target_id": str(target) if target else None, "available": True, "completed": None,
            "status": "suggestion", "status_message": "学习建议", "action_label": "打开", "attempt_id": None, "completed_at": None}
        if kind == "assignment":
            assignment = context["assignments"].get(target)
            if not assignment or assignment.course_id != plan.course_id or assignment.status not in {"published", "closed"}:
                result.update(available=False, status="unavailable", status_message="作业已不可访问")
            else:
                submission = context["submissions"].get(target)
                result.update(completed=bool(submission), due_at=assignment.due_at,
                    status="completed" if submission else "pending", action_label="查看提交" if submission else "打开作业",
                    status_message=(f"已批改 {submission.score:g}/{submission.max_score:g}" if submission and submission.status == "graded" else
                        "已提交，等待批改" if submission else cls._assignment_hint(assignment, context)),
                    completed_at=submission.submitted_at if submission else None)
                if not submission and assignment.status == "closed":
                    result.update(available=False, status="unavailable", status_message="作业已关闭")
        elif kind in {"wrong_question", "practice_question"}:
            question = context["questions"].get(target)
            if not question or question.course_id != plan.course_id:
                result.update(available=False, status="unavailable", status_message="原题已不可访问")
            else:
                try:
                    scheduled = utc(datetime.fromisoformat(raw["scheduled_at"])) if raw.get("scheduled_at") else utc(plan.created_at)
                except (ValueError, TypeError):
                    scheduled = utc(plan.created_at)
                attempts = [row for row in context["attempts"].get(target, []) if utc(row.attempted_at) >= scheduled]
                correct = next((row for row in attempts if row.is_correct is True), None)
                feedback = correct or (attempts[-1] if attempts else None)
                result.update(completed=bool(correct), status="completed" if correct else "in_progress" if attempts else "pending",
                    action_label="查看本次复盘" if feedback else "开始练习", attempt_id=str(feedback.id) if feedback else None,
                    completed_at=correct.attempted_at if correct else None,
                    status_message="已完成本次练习目标" if correct else "已作答，可复盘后继续巩固" if feedback else "完成一次独立练习")
                blocked = cls._blocked(context).get(target)
                if blocked and not correct:
                    result.update(status="assignment_first", action_label="先查看对应作业", status_message="原题已用于待交作业，先处理作业")
        elif kind == "wrong_review":
            remaining = sum(1 for qid, wrong in context["wrong"].items() if qid in context["questions"]
                and context["questions"][qid].course_id == plan.course_id and not wrong.mastered)
            result.update(completed=remaining == 0, status="completed" if remaining == 0 else "pending",
                status_message="旧版错题汇总，可更新为逐题安排", action_label="查看课程错题")
        elif kind == "section_preview":
            if target not in {row.id for row in context["sections"][plan.course_id]}:
                result.update(available=False, status="unavailable", status_message="章节已调整")
            else:
                result.update(action_label="查看章节", status_message="预习建议")
        elif kind == "course_review":
            result.update(action_label="查看课程", status_message="课程回顾建议")
        else:
            result.update(kind="course_review", available=False, status="unavailable", status_message="旧任务类型已不可用")
        return result

    @classmethod
    def _item(cls, plan, course, context):
        items = [cls._render_item(plan, raw, context) for raw in plan.items]
        trackable = [item for item in items if item["available"] and item["completed"] is not None]
        complete = sum(item["completed"] is True for item in trackable)
        pending = next((item for item in items if item["available"] and item["completed"] is False), None)
        legacy = plan.source_context.get("format") != 2
        needs = legacy or plan.source_context.get("signature") != cls._signature(course, context)
        feedback = ("本次可追踪任务已完成，可回看复盘或更新下一步安排。" if trackable and complete == len(trackable) else
            f"已完成 {complete} 项；建议下一步：{pending['title']}。" if pending else "可以先回顾课程资料，再安排下一步练习。")
        return {"id": str(plan.id), "course_id": str(course.id), "course_title": course.title, "created_at": plan.created_at,
            "items": items, "actionable_count": len(trackable), "completed_count": complete, "revision": plan.revision,
            "previous_plan_id": str(plan.previous_plan_id) if plan.previous_plan_id else None,
            "preferences": StudyPlanPreferences.model_validate(plan.preferences or {}).model_dump(),
            "needs_refresh": needs, "legacy_plan": legacy, "change_summary": plan.source_context.get("changes", {}),
            "next_item_id": pending["id"] if pending else None, "feedback": feedback}

    @classmethod
    def _candidates(cls, course, context, preferences):
        now = context["now"]
        slots = {10: 2, 20: 4, 40: 6, 60: 8}[preferences["daily_minutes"]]
        pending = [row for row in context["assignments"].values() if row.course_id == course.id
            and row.status == "published" and row.id not in context["submissions"]]
        pending.sort(key=lambda row: (bool(row.due_at and utc(row.due_at) < now),
            -utc(row.due_at).timestamp() if row.due_at and utc(row.due_at) < now else utc(row.due_at).timestamp() if row.due_at else float("inf"), str(row.id)))
        blocked = cls._blocked(context)
        eligible = [row for row in context["questions"].values() if row.course_id == course.id and row.question_type != "short_answer" and row.id not in blocked]
        wrong = sorted([row for row in eligible if row.id in context["wrong"] and not context["wrong"][row.id].mastered],
            key=lambda row: (-context["wrong"][row.id].wrong_count, row.difficulty, str(row.id)))
        unseen = sorted([row for row in eligible if not context["attempts"].get(row.id) and row not in wrong], key=lambda row: (row.difficulty, str(row.id)))
        assignments = [{"kind": "assignment", "target_id": str(row.id), "title": row.title,
            "detail": cls._assignment_hint(row, context), "due_at": iso(row.due_at),
            "estimated_minutes": min(40, max(10, len(context["links"].get(row.id, [])) * 4))} for row in pending[:3]]
        practice = [{"kind": "wrong_question" if row in wrong else "practice_question", "target_id": str(row.id),
            "title": f"{'再练' if row in wrong else '练习'}：{row.knowledge_point or '课程知识'}", "detail": row.stem[:180],
            "knowledge_point": row.knowledge_point, "due_at": None, "estimated_minutes": 5} for row in [*wrong[:3], *unseen[:2]]]
        urgent = assignments[:1] if pending and pending[0].due_at and now <= utc(pending[0].due_at) <= now + timedelta(days=2) else []
        if preferences["focus"] == "assignments":
            ordered = [*assignments, *practice]
        elif preferences["focus"] == "review":
            ordered = [*urgent, *practice, *assignments]
        else:
            ordered = [*assignments[:1], *practice[:2], *assignments[1:], *practice[2:]]
        chosen, used, estimated = [], set(), 0
        for item in ordered:
            key = (item["kind"], item["target_id"])
            cost = item.get("estimated_minutes", 5)
            if chosen and estimated + cost > preferences["daily_minutes"]:
                continue
            if key not in used:
                chosen.append(item)
                used.add(key)
                estimated += cost
            if len(chosen) >= slots:
                break
        sections = context["sections"][course.id]
        sessions = context["sessions"][course.id]
        for section in sections:
            linked = [row for row in sessions if row.section_id == section.id]
            if ((linked and any(not row.completed for row in linked)) or not sessions) and estimated + 5 <= preferences["daily_minutes"]:
                chosen.append({"kind": "section_preview", "target_id": str(section.id), "title": f"预习：{section.title}",
                    "detail": "打开章节和对应课程资料", "due_at": None, "estimated_minutes": 5})
                break
        return chosen or [{"kind": "course_review", "target_id": str(course.id), "title": "回顾本课程", "detail": "打开课程大纲与资料", "due_at": None}]

    def _save(self, session, student_id, course, previous, preferences, context):
        preferences = StudyPlanPreferences.model_validate(preferences or {}).model_dump()
        current = [self._render_item(previous, row, context) for row in previous.items] if previous else []
        unfinished = {(row["kind"], row.get("target_id")): row for row in current if row["completed"] is not True}
        completed = sorted([row for row in current if row["completed"] is True],
            key=lambda row: utc(row["completed_at"]).timestamp() if row.get("completed_at") else 0, reverse=True)[:6]
        selected = self._candidates(course, context, preferences)
        items = []
        for row in selected:
            old = unfinished.get((row["kind"], row.get("target_id")))
            items.append({**row, "id": old["id"] if old else str(uuid4()),
                "scheduled_at": old.get("scheduled_at", iso(previous.created_at)) if old and previous else iso(context["now"])})
        current_ids = {row["id"] for row in items}
        # Keep achieved goals, never rewrite the prior revision or mark new goals done.
        for row in completed:
            if row["id"] in current_ids:
                continue
            stored = {key: value for key, value in row.items() if key in {
                "id", "kind", "target_id", "title", "detail", "due_at", "estimated_minutes", "knowledge_point", "scheduled_at"}}
            if isinstance(stored.get("due_at"), datetime):
                stored["due_at"] = iso(stored["due_at"])
            stored.setdefault("scheduled_at", iso(previous.created_at))
            items.append(stored)
        plan = StudyPlan(student_id=student_id, course_id=course.id, items=items, preferences=preferences,
            previous_plan_id=previous.id if previous else None, revision=(previous.revision + 1) if previous else 1,
            source_context={"format": 2, "signature": self._signature(course, context), "changes": {
                "new_tasks": sum(row["id"] not in {item["id"] for item in current} for row in items),
                "kept_completed": len(completed), "previous_task_count": len(previous.items) if previous else 0}})
        session.add(plan)
        session.flush()
        actor_name = session.scalar(select(User.display_name).where(User.id == student_id)) or "学生"
        session.add(AuditLog(actor_id=student_id, actor_name=actor_name, action="refresh_study_plan" if previous else "create_study_plan",
            resource_type="study_plan", resource_id=str(plan.id), detail={"course_id": str(course.id), "revision": plan.revision,
                "previous_plan_id": str(previous.id) if previous else None, "task_count": len(items)}))
        session.commit()
        return self._item(plan, course, context)

    def create(self, *, student_id, course_id, preferences=None):
        with self._session_factory() as session:
            try:
                course = self._course(session, student_id, course_id, lock=True)
            except LookupError:
                return None
            previous = self._latest(session, student_id, course_id)
            return self._save(session, student_id, course, previous, preferences, self._context(session, student_id, [course_id]))

    def refresh(self, plan_id, *, student_id, preferences=None):
        with self._session_factory() as session:
            plan, course = self._plan(session, student_id, plan_id)
            self._course(session, student_id, course.id, lock=True)
            latest = self._latest(session, student_id, course.id)
            context = self._context(session, student_id, [course.id])
            if latest.id != plan.id:
                return {**self._item(latest, course, context), "refresh_notice": "已有较新的安排，已恢复最新版本；请核对后再更新。"}
            prefs = StudyPlanPreferences.model_validate(preferences or plan.preferences or {}).model_dump()
            if plan.source_context.get("signature") == self._signature(course, context) and prefs == plan.preferences:
                return {**self._item(plan, course, context), "refresh_notice": "当前安排已是最新，无需重复生成。"}
            return self._save(session, student_id, course, latest, prefs, context)

    def list_current(self, *, student_id):
        with self._session_factory() as session:
            ranked = select(StudyPlan.id.label("plan_id"), func.row_number().over(partition_by=StudyPlan.course_id,
                order_by=(StudyPlan.revision.desc(), StudyPlan.created_at.desc(), StudyPlan.id.desc())).label("position")).where(StudyPlan.student_id == student_id).subquery()
            rows = session.execute(select(StudyPlan, Course).join(ranked, ranked.c.plan_id == StudyPlan.id)
                .join(Course, Course.id == StudyPlan.course_id).join(CourseEnrollment, CourseEnrollment.course_id == Course.id)
                .where(ranked.c.position == 1, CourseEnrollment.user_id == student_id,
                    CourseEnrollment.status == "active", Course.status == "published").order_by(StudyPlan.created_at.desc(), StudyPlan.id.desc())).all()
            if not rows:
                return []
            context = self._context(session, student_id, [course.id for _, course in rows])
            return [self._item(plan, course, context) for plan, course in rows]

    def get(self, plan_id, *, student_id):
        with self._session_factory() as session:
            plan, course = self._plan(session, student_id, plan_id)
            return self._item(plan, course, self._context(session, student_id, [course.id]))

    def history(self, course_id, *, student_id, page, page_size):
        with self._session_factory() as session:
            self._course(session, student_id, course_id)
            return sql_page(session, select(StudyPlan).where(StudyPlan.student_id == student_id, StudyPlan.course_id == course_id)
                .order_by(StudyPlan.revision.desc(), StudyPlan.created_at.desc(), StudyPlan.id.desc()), page=page, page_size=page_size, mapper=lambda row: {
                    "id": str(row.id), "revision": row.revision, "created_at": row.created_at,
                    "task_count": len(row.items), "preferences": row.preferences or {}})

    def target(self, plan_id, item_id, *, student_id):
        with self._session_factory() as session:
            plan, course = self._plan(session, student_id, plan_id)
            raw = next((row for row in plan.items if identifier(row.get("id")) == item_id), None)
            if raw is None:
                raise LookupError("任务不存在。")
            context = self._context(session, student_id, [course.id])
            item = self._render_item(plan, raw, context)
            if not item["available"]:
                raise LookupError("原任务已不可访问，请更新学习安排。")
            target = item["target_id"]
            kind = item["kind"]
            result = {"course_id": str(course.id), "target_id": target or str(course.id)}
            if kind == "assignment":
                return {**result, "kind": "assignment"}
            if kind in {"wrong_question", "practice_question"}:
                if item["status"] == "assignment_first":
                    return {**result, "kind": "assignment", "target_id": str(self._blocked(context)[UUID(target)])}
                return {**result, "kind": "practice_feedback" if item.get("attempt_id") else "question", "attempt_id": item.get("attempt_id"),
                    "practice_source": "wrong_question" if kind == "wrong_question" else "diagnostic"}
            if kind == "wrong_review":
                first = next((qid for qid, row in context["wrong"].items() if not row.mastered and
                    context["questions"][qid].course_id == course.id and qid not in self._blocked(context)), None)
                return {**result, "kind": "question" if first else "course", "target_id": str(first or course.id), "practice_source": "wrong_question" if first else None}
            return {**result, "kind": "section"} if kind == "section_preview" else {**result, "kind": "course", "target_id": str(course.id)}
