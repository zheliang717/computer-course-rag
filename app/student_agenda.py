"""Answer timetable and assignment questions from authorized platform records."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.models import Assignment, AssignmentSubmission, Course, CourseEnrollment, CourseSession, LateSubmissionRequest


CHINA_TIME = timezone(timedelta(hours=8))


class StudentAgendaService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _intents(question: str) -> tuple[int | None, bool, bool, bool, bool]:
        compact = re.sub(r"\s+", "", question)
        tomorrow = bool(re.search(r"(?:明天|明日).*?(?:什么课|哪些课|有课|上课|课程表|课表)|"
                                  r"(?:课表|课程表).*?(?:明天|明日)", compact))
        today = bool(re.search(r"(?:今天|今日).*?(?:什么课|哪些课|有课|上课|课程表|课表)|"
                               r"(?:课表|课程表).*?(?:今天|今日)", compact))
        today = today or bool(re.fullmatch(r"(?:我的)?(?:课表|课程表)[？?]?", compact))
        day_offset = 1 if tomorrow else 0 if today else None
        next_class = bool(re.search(r"(?:下一节|下节|下一次|最近).*?课", compact))
        next_assignment = bool(re.search(r"(?:下一个|下一项|最近|即将).*?作业", compact))
        late_status = bool(re.search(r"(?:补交|逾期).*?(?:申请|作业|状态)|"
                                     r"(?:申请|作业|状态).*?(?:补交|逾期)", compact))
        assignments = next_assignment or bool(re.search(
            r"(?:待交|待完成).*?作业|作业.*?(?:截止|到期)", compact)) or late_status
        return day_offset, next_class, assignments, next_assignment, late_status

    def answer(self, *, user_id: UUID, question: str, course_id: UUID | None = None,
               now: datetime | None = None) -> dict | None:
        day_offset, wants_next_class, wants_assignments, wants_next_assignment, wants_late_status = self._intents(question)
        if day_offset is None and not wants_next_class and not wants_assignments:
            return None
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        local_now = current.astimezone(CHINA_TIME)
        target_date = local_now.date() + timedelta(days=day_offset or 0)
        day_start = datetime.combine(target_date, time.min, tzinfo=CHINA_TIME).astimezone(timezone.utc)
        day_end = day_start + timedelta(days=1)

        with self._session_factory() as session:
            enrolled = session.execute(select(Course.id, Course.title).join(
                CourseEnrollment, CourseEnrollment.course_id == Course.id,
            ).where(CourseEnrollment.user_id == user_id, CourseEnrollment.status == "active",
                    Course.status == "published")).all()
            courses = {course_key: title for course_key, title in enrolled}
            if course_id is not None and course_id not in courses:
                raise PermissionError("课程不存在或当前学生未加入。")
            scoped_ids = [course_id] if course_id is not None else list(courses)
            if not scoped_ids:
                return self._empty_answer(day_offset, wants_next_class, wants_assignments, wants_late_status, target_date)

            lines: list[str] = []
            actions: list[dict[str, str]] = []
            if day_offset is not None:
                classes = list(session.scalars(select(CourseSession).where(
                    CourseSession.course_id.in_(scoped_ids),
                    CourseSession.session_date >= day_start, CourseSession.session_date < day_end,
                ).order_by(CourseSession.session_date, CourseSession.id)).all())
                lines.append(f"### {'明天' if day_offset else '今天'}的课 · {target_date:%Y-%m-%d}")
                if classes:
                    for item in classes[:8]:
                        starts = self._local(item.session_date).strftime("%H:%M")
                        location = item.location or "地点待定"
                        title = courses[item.course_id]
                        lines.append(f"- {starts} · **{title}** · {item.title} · {location}"
                                      + ("（已完成）" if item.completed else ""))
                        actions.append({"kind": "course", "target_id": str(item.course_id),
                                        "title": f"{starts} · {title}", "detail": f"{item.title} · {location}"})
                else:
                    lines.append(f"当前课程没有安排在{'明天' if day_offset else '今天'}的课次。请以教师发布的课程安排为准。")

            if wants_next_class:
                upcoming = session.scalar(select(CourseSession).where(
                    CourseSession.course_id.in_(scoped_ids), CourseSession.completed.is_(False),
                    CourseSession.session_date >= current.astimezone(timezone.utc),
                ).order_by(CourseSession.session_date, CourseSession.id).limit(1))
                if lines:
                    lines.append("")
                lines.append("### 下一节课")
                if upcoming:
                    when = self._local(upcoming.session_date).strftime("%m月%d日 %H:%M")
                    location = upcoming.location or "地点待定"
                    title = courses[upcoming.course_id]
                    lines.append(f"- **{title} · {upcoming.title}**：{when}，{location}")
                    actions.append({"kind": "course", "target_id": str(upcoming.course_id),
                                    "title": f"{when} · {title}", "detail": f"{upcoming.title} · {location}"})
                else:
                    lines.append("当前课程没有即将开始的已安排课次。")

            if wants_assignments:
                assignments = list(session.scalars(select(Assignment).where(
                    Assignment.course_id.in_(scoped_ids), Assignment.status == "published",
                )).all())
                submitted = set(session.scalars(select(AssignmentSubmission.assignment_id).where(
                    AssignmentSubmission.student_id == user_id,
                    AssignmentSubmission.assignment_id.in_([item.id for item in assignments]),
                )).all()) if assignments else set()
                pending = [item for item in assignments if item.id not in submitted]
                late_requests = {item.assignment_id: item for item in session.scalars(select(LateSubmissionRequest).where(
                    LateSubmissionRequest.student_id == user_id,
                    LateSubmissionRequest.assignment_id.in_([item.id for item in pending]),
                )).all()} if pending else {}
                current_utc = current.astimezone(timezone.utc)
                upcoming = [item for item in pending if not item.due_at or self._utc(item.due_at) >= current_utc]
                overdue = [item for item in pending if item.due_at and self._utc(item.due_at) < current_utc]
                approved_overdue = [item for item in overdue if self._late_note(late_requests.get(item.id), current_utc)[1]]
                upcoming.sort(key=lambda item: (self._utc(item.due_at) if item.due_at else datetime.max.replace(tzinfo=timezone.utc),
                                                item.title))
                overdue.sort(key=lambda item: self._utc(item.due_at), reverse=True)
                approved_overdue.sort(key=lambda item: (
                    self._utc(late_requests[item.id].approved_until)
                    if late_requests[item.id].approved_until else datetime.max.replace(tzinfo=timezone.utc), item.title))
                if lines:
                    lines.append("")
                lines.append("### 下一个作业" if wants_next_assignment else
                             "### 补交与逾期作业" if wants_late_status else "### 待交作业")
                other_overdue = [item for item in overdue if item not in approved_overdue]
                candidates = (approved_overdue + other_overdue) if wants_late_status else (
                    upcoming + approved_overdue + other_overdue if wants_next_assignment else
                    approved_overdue + upcoming + other_overdue)
                if candidates:
                    if wants_next_assignment and not upcoming:
                        lines.append("当前没有尚未截止的作业；" + (
                            "下面是已获批可提交的补交作业。" if approved_overdue else
                            "下面这项已逾期，请查看补交申请。"))
                    shown = candidates[:1] if wants_next_assignment else candidates[:3]
                    for item in shown:
                        due_at = self._local(item.due_at).strftime("%m月%d日 %H:%M") if item.due_at else "未设截止时间"
                        is_overdue = bool(item.due_at and self._utc(item.due_at) < current_utc)
                        note = self._late_note(late_requests.get(item.id), current_utc)[0] if is_overdue else ""
                        title = courses[item.course_id]
                        lines.append(f"- **{title} · {item.title}**：{due_at}{note}")
                        actions.append({"kind": "assignment", "target_id": str(item.id),
                                        "title": item.title, "detail": f"{title} · {due_at}{note}"})
                else:
                    lines.append("当前课程没有需要处理的补交或逾期作业。" if wants_late_status else
                                 "当前课程没有待交的已发布作业。")

            return {"answer": "\n".join(lines), "actions": actions, "source_course_ids": [str(item) for item in scoped_ids]}

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

    @classmethod
    def _local(cls, value: datetime) -> datetime:
        return cls._utc(value).astimezone(CHINA_TIME)

    @classmethod
    def _late_note(cls, request: LateSubmissionRequest | None, current_utc: datetime) -> tuple[str, bool]:
        if request is None:
            return "（已截止，请查看补交申请）", False
        if request.status == "pending":
            return "（补交申请待教师审批）", False
        if request.status == "approved":
            if request.approved_until and cls._utc(request.approved_until) <= current_utc:
                return "（补交批准已过期，可重新申请）", False
            deadline = f"，请在{cls._local(request.approved_until).strftime('%m月%d日 %H:%M')}前提交" if request.approved_until else "，可提交"
            return f"（获批补交{deadline}）", True
        if request.status == "rejected":
            return "（补交申请未通过，可重新申请）", False
        return "（补交状态需查看作业详情）", False

    @staticmethod
    def _empty_answer(day_offset: int | None, wants_next_class: bool,
                      wants_assignments: bool, wants_late_status: bool, target_date: date) -> dict:
        lines = []
        if day_offset is not None:
            lines.append(f"### {'明天' if day_offset else '今天'}的课 · {target_date:%Y-%m-%d}\n当前没有可访问的已发布课程课次。")
        if wants_next_class:
            lines.append("### 下一节课\n当前没有可访问的已发布课程课次。")
        if wants_assignments:
            lines.append(("### 补交与逾期作业" if wants_late_status else "### 待交作业")
                         + "\n当前没有可访问的已发布课程作业。")
        return {"answer": "\n\n".join(lines), "actions": []}
