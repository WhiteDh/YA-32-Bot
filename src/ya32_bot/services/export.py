"""Calendar export (.ics) and subject search over the computed schedule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.core.timetable import Lesson
from ya32_bot.db.models import Homework
from ya32_bot.services import homework, schedule, semester

ICS_WEEKS = 8


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """RFC 5545: lines over 75 octets are folded with CRLF + space."""
    out: list[str] = []
    raw = line.encode()
    while len(raw) > 75:
        cut = 75
        while (raw[cut] & 0xC0) == 0x80:  # never split a UTF-8 sequence
            cut -= 1
        out.append(raw[:cut].decode())
        raw = b" " + raw[cut:]
    out.append(raw.decode())
    return out


def build_ics(lessons: list[Lesson], tz: str, *, stamp: datetime, show_room: bool) -> str:
    zone = ZoneInfo(tz)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//YA-32//Schedule bot//UK",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:ЯА-32 · розклад",
        f"X-WR-TIMEZONE:{tz}",
    ]
    utc_stamp = stamp.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    for lesson in lessons:
        if lesson.cancelled:
            continue
        start = lesson.starts_at().replace(tzinfo=zone).astimezone(ZoneInfo("UTC"))
        end = lesson.ends_at().replace(tzinfo=zone).astimezone(ZoneInfo("UTC"))
        description = [lesson.kind.label]
        if lesson.teacher:
            description.append(lesson.teacher)
        if lesson.note:
            description.append(lesson.note)
        lines += [
            "BEGIN:VEVENT",
            f"UID:ya32-{lesson.date:%Y%m%d}-{lesson.slot}@ya32-bot",
            f"DTSTAMP:{utc_stamp}",
            f"DTSTART:{start:%Y%m%dT%H%M%SZ}",
            f"DTEND:{end:%Y%m%dT%H%M%SZ}",
            f"SUMMARY:{_ics_escape(f'{lesson.kind.emoji} {lesson.subject}')}",
            f"DESCRIPTION:{_ics_escape(chr(10).join(description))}",
        ]
        if show_room and lesson.room:
            lines.append(f"LOCATION:{_ics_escape(lesson.room)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"


async def ics_for_user(session: AsyncSession, today: date, tz: str, *, now: datetime, show_room: bool) -> str:
    sem = await semester.get_semester(session)
    end = today + timedelta(weeks=ICS_WEEKS)
    if sem.end and sem.end < end:
        end = max(sem.end, today)
    bundles = await schedule.days(session, today, end, today=today)
    lessons = [lesson for b in bundles for lesson in b.day.lessons]
    return build_ics(lessons, tz, stamp=now.replace(tzinfo=ZoneInfo(tz)), show_room=show_room)


@dataclass(frozen=True, slots=True)
class SearchHit:
    subject: str
    upcoming: list[Lesson]
    homework: list[Homework]


async def search(session: AsyncSession, query: str, today: date, *, limit: int = 4) -> list[SearchHit]:
    needle = query.strip().lower()
    if len(needle) < 3:
        return []
    extras = await schedule.subjects(session)
    names = [
        n for n in await schedule.known_subject_names(session)
        if needle in n.lower() or (extras.get(n) and needle in (extras[n].short or "").lower())
    ]  # fmt: skip
    if not names:
        return []
    lessons = await schedule.upcoming_lessons(session, today, horizon=28)
    hits = []
    for name in names[:5]:
        upcoming = sorted((x for x in lessons if x.subject == name), key=Lesson.starts_at)[:limit]
        hits.append(SearchHit(name, upcoming, await homework.for_subject(session, name, today, limit=3)))
    return hits
