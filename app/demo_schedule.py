"""Calendar slots for the clearly identified, disposable demo courses."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone


CHINA_TIME = timezone(timedelta(hours=8))
DEMO_DURATION_MINUTES = 100
DEMO_SLOTS = {
    "DSA-2026": (0, 8, 0, 12, 5),
    "OS-2026": (2, 10, 0, 10, 4),
    "NET-2026": (4, 14, 0, 8, 3),
}


def to_china_time(value: datetime) -> datetime:
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(CHINA_TIME)


def current_demo_semester(now: datetime) -> str:
    local = to_china_time(now)
    academic_start = local.year if local.month >= 8 else local.year - 1
    term = "第一学期" if local.month >= 8 or local.month <= 1 else "第二学期"
    return f"{academic_start}-{academic_start + 1} {term}"


def demo_session_dates(now: datetime, course_code: str) -> list[datetime]:
    weekday, hour, minute, total, completed = DEMO_SLOTS[course_code]
    local = to_china_time(now)
    next_day = local.date() + timedelta(days=(weekday - local.weekday()) % 7)
    next_slot = datetime.combine(next_day, time(hour, minute), tzinfo=CHINA_TIME)
    if next_slot <= local:
        next_slot += timedelta(weeks=1)
    first_slot = next_slot - timedelta(weeks=completed)
    return [(first_slot + timedelta(weeks=index)).astimezone(timezone.utc)
            for index in range(total)]


def is_legacy_demo_schedule(values: list[datetime]) -> bool:
    """Only the original seeder's Monday 17:57 weekly pattern is auto-repairable."""
    local = [to_china_time(value) for value in values]
    return bool(local) and all(item.weekday() == 0 and item.hour == 17 and item.minute == 57
                               for item in local) and all(
        local[index + 1] - local[index] == timedelta(weeks=1)
        for index in range(len(local) - 1)
    )
