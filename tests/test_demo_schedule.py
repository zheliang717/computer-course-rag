"""Demo course slots must agree with their published weekday and time."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.demo_schedule import CHINA_TIME, DEMO_DURATION_MINUTES, DEMO_SLOTS, current_demo_semester, demo_session_dates, to_china_time
from app.models import AuditLog, Course, CourseSession
from scripts.align_demo_schedule import DEMO_COURSES, align_demo_schedule


NOW = datetime(2026, 9, 29, 17, tzinfo=timezone.utc)  # 9 月 30 日 01:00（中国标准时间）


def test_generated_demo_slots_match_timetable_and_completed_boundary() -> None:
    assert current_demo_semester(NOW) == "2026-2027 第一学期"
    for code, (weekday, hour, minute, total, completed) in DEMO_SLOTS.items():
        dates = demo_session_dates(NOW, code)
        assert len(dates) == total
        local = [to_china_time(value) for value in dates]
        assert all(item.weekday() == weekday and (item.hour, item.minute) == (hour, minute)
                   for item in local)
        assert dates[completed - 1] < NOW < dates[completed]
        assert all(dates[index + 1] - dates[index] == timedelta(weeks=1)
                   for index in range(len(dates) - 1))


def test_repair_only_untouched_legacy_demo_sessions_and_audits() -> None:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    first_legacy = datetime(2026, 8, 24, 17, 57, tzinfo=CHINA_TIME)
    course_ids = {}
    with sessions.begin() as session:
        for course_index, (code, (title, schedule, location)) in enumerate(DEMO_COURSES.items()):
            course_id = uuid4()
            course_ids[code] = course_id
            session.add(Course(id=course_id, code=code, title=title, schedule=schedule,
                               location=location, status="published",
                               semester="2026-2027 第二学期" if code == "NET-2026" else "2026-2027 第一学期"))
            _weekday, _hour, _minute, total, completed = DEMO_SLOTS[code]
            for index in range(total):
                session.add(CourseSession(
                    course_id=course_id, title=f"第 {index + 1} 次课：演示",
                    session_date=(first_legacy + timedelta(weeks=course_index + index)).astimezone(timezone.utc),
                    duration_minutes=90, location=location, completed=index < completed,
                ))

    dry = align_demo_schedule(sessions, now=NOW, apply=False)
    assert all(item["status"] == "待修正" for item in dry)
    with sessions() as session:
        assert list(session.scalars(select(AuditLog)).all()) == []
        assert to_china_time(session.scalar(select(CourseSession).where(
            CourseSession.course_id == course_ids["DSA-2026"]).order_by(CourseSession.session_date)
        ).session_date).hour == 17

    applied = align_demo_schedule(sessions, now=NOW, apply=True)
    assert all(item["status"] == "待修正" for item in applied)
    with sessions() as session:
        assert len(list(session.scalars(select(AuditLog).where(
            AuditLog.action == "align_demo_schedule")).all())) == 3
        for code, course_id in course_ids.items():
            stored = list(session.scalars(select(CourseSession).where(
                CourseSession.course_id == course_id).order_by(CourseSession.session_date)).all())
            assert [to_china_time(item.session_date).weekday() for item in stored] == [DEMO_SLOTS[code][0]] * len(stored)
            assert (to_china_time(stored[0].session_date).hour,
                    to_china_time(stored[0].session_date).minute) == DEMO_SLOTS[code][1:3]
            assert all(item.duration_minutes == DEMO_DURATION_MINUTES for item in stored)
            assert session.get(Course, course_id).semester == "2026-2027 第一学期"
    again = align_demo_schedule(sessions, now=NOW, apply=True)
    assert all(item["status"] == "已对齐" for item in again)

    with sessions.begin() as session:
        os_sessions = list(session.scalars(select(CourseSession).where(
            CourseSession.course_id == course_ids["OS-2026"])).all())
        original_dates = [item.session_date for item in os_sessions]
        for item in os_sessions:
            item.duration_minutes = 90
    duration_only = align_demo_schedule(sessions, now=NOW, apply=True)
    assert next(item for item in duration_only if item["course"] == "OS-2026")["status"] == "待修正"
    with sessions() as session:
        os_sessions = list(session.scalars(select(CourseSession).where(
            CourseSession.course_id == course_ids["OS-2026"])).all())
        assert [item.session_date for item in os_sessions] == original_dates
        assert all(item.duration_minutes == DEMO_DURATION_MINUTES for item in os_sessions)
        assert len(list(session.scalars(select(AuditLog).where(
            AuditLog.action == "align_demo_schedule")).all())) == 4

    with sessions.begin() as session:
        changed = session.scalar(select(CourseSession).where(
            CourseSession.course_id == course_ids["NET-2026"]))
        changed.duration_minutes = 95
    with pytest.raises(ValueError, match="课次时长已被调整"):
        align_demo_schedule(sessions, now=NOW, apply=True)

    with sessions.begin() as session:
        changed = session.scalar(select(CourseSession).where(
            CourseSession.course_id == course_ids["NET-2026"]))
        changed.duration_minutes = DEMO_DURATION_MINUTES
        changed = session.scalar(select(CourseSession).where(
            CourseSession.course_id == course_ids["OS-2026"]).order_by(CourseSession.session_date))
        changed.session_date += timedelta(hours=1)
    with pytest.raises(ValueError, match="已被调整|不是旧版"):
        align_demo_schedule(sessions, now=NOW, apply=True)
    with sessions() as session:
        assert len(list(session.scalars(select(AuditLog).where(
            AuditLog.action == "align_demo_schedule")).all())) == 4
