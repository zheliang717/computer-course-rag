"""Repair only untouched legacy demo slots; dry-run unless --apply is supplied."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import get_session_factory
from app.demo_schedule import CHINA_TIME, DEMO_DURATION_MINUTES, DEMO_SLOTS, current_demo_semester, demo_session_dates, is_legacy_demo_schedule, to_china_time
from app.models import AuditLog, Course, CourseSession


DEMO_COURSES = {
    "DSA-2026": ("数据结构与算法", "周一 08:00-09:40", "博学楼 A203"),
    "OS-2026": ("操作系统原理", "周三 10:00-11:40", "计算机楼 302"),
    "NET-2026": ("计算机网络", "周五 14:00-15:40", "实验楼 B406"),
}


def align_demo_schedule(session_factory, *, now: datetime, apply: bool) -> list[dict]:
    local_now = now.astimezone(CHINA_TIME)
    expected_semester = current_demo_semester(now)
    changes: list[tuple[Course, list[CourseSession], list[datetime], str, int]] = []
    summary: list[dict] = []
    with session_factory() as session:
        for code, (title, schedule, location) in DEMO_COURSES.items():
            course = session.scalar(select(Course).where(Course.code == code).with_for_update())
            if course is None or (course.title, course.schedule, course.location, course.status) != (
                title, schedule, location, "published"
            ):
                raise ValueError(f"{code} 不再符合预置演示课程，未修改任何课次。")
            sessions = list(session.scalars(select(CourseSession).where(
                CourseSession.course_id == course.id).order_by(CourseSession.session_date).with_for_update()).all())
            weekday, hour, minute, total, completed = DEMO_SLOTS[code]
            if len(sessions) != total or any(
                not item.title.startswith(f"第 {index + 1} 次课：")
                or item.completed != (index < completed) or item.location != location
                for index, item in enumerate(sessions)
            ):
                raise ValueError(f"{code} 的课次已被调整，未修改任何课次。")
            durations = {item.duration_minutes for item in sessions}
            if len(durations) != 1 or durations.pop() not in {90, DEMO_DURATION_MINUTES}:
                raise ValueError(f"{code} 的课次时长已被调整，未修改任何课次。")
            old_duration = sessions[0].duration_minutes
            local_dates = [to_china_time(item.session_date) for item in sessions]
            aligned = all(item.weekday() == weekday and item.hour == hour and item.minute == minute
                          for item in local_dates) and all(
                local_dates[index + 1] - local_dates[index] == timedelta(weeks=1)
                for index in range(len(local_dates) - 1))
            legacy = is_legacy_demo_schedule([item.session_date for item in sessions])
            if not aligned and not legacy:
                raise ValueError(f"{code} 的课次不是旧版演示模式，未修改任何课次。")
            allowed_semesters = {expected_semester}
            if code == "NET-2026":
                allowed_semesters.add("2026-2027 第二学期")
            if course.semester not in allowed_semesters or (aligned and course.semester != expected_semester):
                raise ValueError(f"{code} 的学期已被调整，未修改任何课次。")
            target_dates = demo_session_dates(now, code) if legacy else [item.session_date for item in sessions]
            needs_update = legacy or old_duration != DEMO_DURATION_MINUTES
            summary.append({
                "course": code, "status": "待修正" if needs_update else "已对齐",
                "current_first": local_dates[0].isoformat(),
                "target_first": target_dates[0].astimezone(CHINA_TIME).isoformat(),
                "session_count": len(sessions),
                "current_duration_minutes": old_duration,
                "target_duration_minutes": DEMO_DURATION_MINUTES,
            })
            if needs_update:
                changes.append((course, sessions, target_dates, course.semester or "", old_duration))
        if apply:
            for course, sessions, target_dates, old_semester, old_duration in changes:
                previous_first = sessions[0].session_date.isoformat()
                for item, target in zip(sessions, target_dates, strict=True):
                    item.session_date = target
                    item.duration_minutes = DEMO_DURATION_MINUTES
                course.semester = expected_semester
                session.add(AuditLog(
                    actor_name="演示数据维护", action="align_demo_schedule",
                    resource_type="course", resource_id=str(course.id),
                    detail={"code": course.code, "session_count": len(sessions),
                            "old_semester": old_semester, "new_semester": expected_semester,
                            "old_first": previous_first, "new_first": target_dates[0].isoformat(),
                            "old_duration_minutes": old_duration,
                            "new_duration_minutes": DEMO_DURATION_MINUTES,
                            "local_time": local_now.isoformat()},
                ))
            session.commit()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="将已核对的演示课次写回数据库")
    args = parser.parse_args()
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://rag:rag@127.0.0.1:5432/rag")
    result = align_demo_schedule(get_session_factory(), now=datetime.now(timezone.utc), apply=args.apply)
    print(json.dumps({"applied": args.apply, "courses": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
