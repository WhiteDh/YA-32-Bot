"""Reading and editing the schedule.

Reading: template + overrides + holidays → :class:`core.timetable.Day`.
Editing: every change goes through :mod:`services.audit` so it can be undone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.core import timetable as tt
from ya32_bot.core.calendar import monday_of
from ya32_bot.core.slots import MAX_SLOT
from ya32_bot.db.models import Homework, Override, Subject, TemplateLesson
from ya32_bot.services import audit, semester


def _to_core_template(row: TemplateLesson) -> tt.TemplateLesson:
    dates: list[date] = []
    for raw in row.dates or []:
        try:
            dates.append(date.fromisoformat(str(raw)))
        except ValueError:
            continue
    return tt.TemplateLesson(
        id=row.id,
        week=row.week,
        weekday=row.weekday,
        slot=row.slot,
        subject=row.subject,
        kind=tt.LessonKind.parse(row.kind),
        teacher=row.teacher,
        room=row.room,
        room_url=row.room_url,
        dates=tuple(dates),
    )


def _to_core_override(row: Override) -> tt.Override:
    return tt.Override(
        id=row.id,
        date=row.date,
        slot=row.slot,
        action=tt.OverrideAction(row.action),
        subject=row.subject,
        kind=tt.LessonKind.parse(row.kind) if row.kind else None,
        teacher=row.teacher,
        room=row.room,
        note=row.note,
    )


@dataclass(frozen=True, slots=True)
class DayBundle:
    """A day plus what rendering needs around it."""

    day: tt.Day
    homework: dict[str, list[Homework]]  # subject → homework due that day
    subjects: dict[str, Subject]


async def templates(session: AsyncSession) -> list[tt.TemplateLesson]:
    rows = await session.scalars(select(TemplateLesson).order_by(TemplateLesson.week, TemplateLesson.weekday))
    return [_to_core_template(r) for r in rows.all()]


async def template_rows(session: AsyncSession, week: int, weekday: int) -> list[TemplateLesson]:
    rows = await session.scalars(
        select(TemplateLesson)
        .where(TemplateLesson.week == week, TemplateLesson.weekday == weekday)
        .order_by(TemplateLesson.slot)
    )
    return list(rows.all())


async def overrides(session: AsyncSession, start: date, end: date) -> list[tt.Override]:
    rows = await session.scalars(
        select(Override).where(and_(Override.date >= start, Override.date <= end)).order_by(Override.id)
    )
    return [_to_core_override(r) for r in rows.all()]


async def subjects(session: AsyncSession) -> dict[str, Subject]:
    rows = await session.scalars(select(Subject))
    return {s.name: s for s in rows.all()}


async def known_subject_names(session: AsyncSession) -> list[str]:
    names = set((await session.scalars(select(TemplateLesson.subject).distinct())).all())
    names |= set((await session.scalars(select(Subject.name))).all())
    return sorted(names)


async def homework_between(session: AsyncSession, start: date, end: date) -> list[Homework]:
    rows = await session.scalars(
        select(Homework).where(and_(Homework.due_date >= start, Homework.due_date <= end)).order_by(Homework.id)
    )
    return list(rows.all())


async def days(session: AsyncSession, start: date, end: date, *, today: date) -> list[DayBundle]:
    anchor = await semester.get_anchor(session, today)
    sem = await semester.get_semester(session)
    tpl = await templates(session)
    ovs = await overrides(session, start, end)
    hw = await homework_between(session, start, end)
    subj = await subjects(session)

    out: list[DayBundle] = []
    current = start
    while current <= end:
        holiday = sem.holiday_on(current)
        day = tt.build_day(
            current,
            anchor.week_of(current),
            tpl,
            ovs,
            holiday=holiday.title if holiday else None,
            out_of_semester=not sem.in_session(current),
        )
        by_subject: dict[str, list[Homework]] = {}
        for item in hw:
            if item.due_date == current:
                by_subject.setdefault(item.subject, []).append(item)
        out.append(DayBundle(day, by_subject, subj))
        current += timedelta(days=1)
    return out


async def day(session: AsyncSession, when: date, *, today: date) -> DayBundle:
    return (await days(session, when, when, today=today))[0]


async def week(session: AsyncSession, any_day: date, *, today: date) -> list[DayBundle]:
    monday = monday_of(any_day)
    return await days(session, monday, monday + timedelta(days=6), today=today)


async def upcoming_lessons(session: AsyncSession, today: date, horizon: int = 7) -> list[tt.Lesson]:
    bundles = await days(session, today, today + timedelta(days=horizon), today=today)
    return [lesson for b in bundles for lesson in b.day.active]


# ── Editing one date ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LessonFields:
    subject: str | None = None
    kind: str | None = None
    teacher: str | None = None
    room: str | None = None
    note: str | None = None


async def _add_override(
    session: AsyncSession, change: audit.Change, when: date, slot: int, action: tt.OverrideAction,
    fields: LessonFields, user_id: int | None,
) -> Override:  # fmt: skip
    row = Override(
        date=when,
        slot=slot,
        action=action.value,
        subject=fields.subject,
        kind=fields.kind,
        teacher=fields.teacher,
        room=fields.room,
        note=fields.note,
        created_by=user_id,
    )
    session.add(row)
    await session.flush()
    change.inserted(row)
    return row


async def _clear_overrides(session: AsyncSession, change: audit.Change, when: date, slot: int) -> int:
    rows = (await session.scalars(select(Override).where(Override.date == when, Override.slot == slot))).all()
    for row in rows:
        change.deleted(row)
        await session.delete(row)
    await session.flush()
    return len(rows)


async def cancel(session: AsyncSession, when: date, slot: int, user_id: int | None, note: str | None = None) -> int:
    change = audit.Change("cancel", f"Скасовано {slot} пару {when:%d.%m}")
    await _clear_overrides(session, change, when, slot)
    await _add_override(session, change, when, slot, tt.OverrideAction.CANCEL, LessonFields(note=note), user_id)
    return (await audit.record(session, user_id, change)).id


async def put(session: AsyncSession, when: date, slot: int, fields: LessonFields, user_id: int | None) -> int:
    """Set what happens at ``slot`` on ``when`` — replaces the template pair or adds a new one."""
    change = audit.Change("put", f"{fields.subject or 'Зміна'} — {slot} пара {when:%d.%m}")
    await _clear_overrides(session, change, when, slot)
    await _add_override(session, change, when, slot, tt.OverrideAction.REPLACE, fields, user_id)
    return (await audit.record(session, user_id, change)).id


async def restore(session: AsyncSession, when: date, slot: int, user_id: int | None) -> int | None:
    change = audit.Change("restore", f"Повернуто {slot} пару {when:%d.%m} як у шаблоні")
    if not await _clear_overrides(session, change, when, slot):
        return None
    return (await audit.record(session, user_id, change)).id


async def move(session: AsyncSession, lesson: tt.Lesson, to_date: date, to_slot: int, user_id: int | None) -> int:
    """Move one concrete pair: cancel it where it was and put a copy at the target."""
    change = audit.Change(
        "move", f"{lesson.subject}: {lesson.slot} пара {lesson.date:%d.%m} → {to_slot} пара {to_date:%d.%m}"
    )
    await _clear_overrides(session, change, lesson.date, lesson.slot)
    if lesson.template_id is not None:
        await _add_override(
            session, change, lesson.date, lesson.slot, tt.OverrideAction.CANCEL,
            LessonFields(note=f"Перенесено на {to_date:%d.%m}, {to_slot} пара"), user_id,
        )  # fmt: skip
    await _clear_overrides(session, change, to_date, to_slot)
    await _add_override(
        session, change, to_date, to_slot, tt.OverrideAction.REPLACE,
        LessonFields(
            subject=lesson.subject, kind=lesson.kind.value, teacher=lesson.teacher, room=lesson.room,
            note=f"Перенесено з {lesson.date:%d.%m}, {lesson.slot} пара",
        ),
        user_id,
    )  # fmt: skip
    return (await audit.record(session, user_id, change)).id


def free_slots(day: tt.Day) -> list[int]:
    taken = {lesson.slot for lesson in day.active}
    return [s for s in range(1, MAX_SLOT + 1) if s not in taken]


# ── Editing the week template ──────────────────────────────────────────────


async def template_add(
    session: AsyncSession, week: int, weekday: int, slot: int, fields: LessonFields, user_id: int | None
) -> TemplateLesson:
    row = TemplateLesson(
        week=week, weekday=weekday, slot=slot, subject=fields.subject or "Пара", kind=fields.kind or "other",
        teacher=fields.teacher, room=fields.room, dates=[], source="manual",
    )  # fmt: skip
    session.add(row)
    await session.flush()
    change = audit.Change("template_add", f"Шаблон: + {row.subject} ({week} тижд., {slot} пара)")
    change.inserted(row)
    await audit.record(session, user_id, change)
    return row


async def template_update(
    session: AsyncSession, row: TemplateLesson, values: dict[str, Any], user_id: int | None
) -> None:
    before = audit.row_to_dict(row)
    for key, value in values.items():
        setattr(row, key, value)
    if "source" not in values:
        row.source = "manual"  # an edited KPI row is now ours — sync "update" leaves it alone
    change = audit.Change("template_edit", f"Шаблон: {row.subject} ({row.week} тижд., {row.slot} пара)")
    change.updated(row, before)
    await session.flush()
    await audit.record(session, user_id, change)


async def template_delete(session: AsyncSession, row: TemplateLesson, user_id: int | None) -> None:
    change = audit.Change("template_delete", f"Шаблон: − {row.subject} ({row.week} тижд., {row.slot} пара)")
    change.deleted(row)
    await session.delete(row)
    await session.flush()
    await audit.record(session, user_id, change)


async def template_clear(session: AsyncSession) -> int:
    rows = (await session.scalars(select(TemplateLesson))).all()
    await session.execute(delete(TemplateLesson))
    return len(rows)


# ── Subjects ───────────────────────────────────────────────────────────────


async def subject_get_or_create(session: AsyncSession, name: str) -> Subject:
    row = await session.scalar(select(Subject).where(Subject.name == name))
    if row is None:
        row = Subject(name=name)
        session.add(row)
        await session.flush()
    return row
