"""Semester bounds, holidays and the week-parity anchor — all editable from the bot."""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.core.calendar import Holiday, Semester, WeekAnchor, monday_of
from ya32_bot.db.models import Holiday as HolidayRow
from ya32_bot.services.kv import kv_get, kv_set

ANCHOR_KEY = "week_anchor"
SEMESTER_KEY = "semester"


async def get_anchor(session: AsyncSession, today: date) -> WeekAnchor:
    raw = await kv_get(session, ANCHOR_KEY)
    if raw.get("date") and raw.get("week") in (1, 2):
        return WeekAnchor(date.fromisoformat(raw["date"]), int(raw["week"]))
    # Nothing configured yet: call the current week the first one.
    return WeekAnchor(monday_of(today), 1)


async def set_anchor(session: AsyncSession, day: date, week: int) -> WeekAnchor:
    anchor = WeekAnchor(monday_of(day), 1 if week == 1 else 2)
    await kv_set(session, ANCHOR_KEY, {"date": anchor.monday.isoformat(), "week": anchor.week})
    return anchor


async def get_semester(session: AsyncSession) -> Semester:
    raw = await kv_get(session, SEMESTER_KEY)
    rows = (await session.scalars(select(HolidayRow).order_by(HolidayRow.start))).all()
    return Semester(
        start=date.fromisoformat(raw["start"]) if raw.get("start") else None,
        end=date.fromisoformat(raw["end"]) if raw.get("end") else None,
        holidays=tuple(Holiday(r.start, r.end, r.title) for r in rows),
    )


async def set_semester_bounds(session: AsyncSession, *, start: date | None = None, end: date | None = None) -> None:
    raw = await kv_get(session, SEMESTER_KEY)
    if start is not None:
        raw["start"] = start.isoformat()
    if end is not None:
        raw["end"] = end.isoformat()
    await kv_set(session, SEMESTER_KEY, raw)


async def clear_semester_bound(session: AsyncSession, which: str) -> None:
    raw = await kv_get(session, SEMESTER_KEY)
    raw.pop(which, None)
    await kv_set(session, SEMESTER_KEY, raw)


async def list_holidays(session: AsyncSession) -> list[HolidayRow]:
    return list((await session.scalars(select(HolidayRow).order_by(HolidayRow.start))).all())


async def add_holiday(session: AsyncSession, start: date, end: date, title: str) -> HolidayRow:
    if end < start:
        start, end = end, start
    row = HolidayRow(start=start, end=end, title=title.strip()[:128] or "Вихідний")
    session.add(row)
    await session.flush()
    return row


async def delete_holiday(session: AsyncSession, holiday_id: int) -> None:
    await session.execute(delete(HolidayRow).where(HolidayRow.id == holiday_id))
