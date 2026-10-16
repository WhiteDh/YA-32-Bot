"""Diff a source against the stored template and apply it in one of three modes.

* ``append``  — «➕ Дозавантажити»: only add what is missing; nothing changes or disappears.
* ``update``  — «🔄 Оновити»: bring KPI-sourced rows in line (add/change/remove);
  rows created or edited by hand (``source="manual"``) are never touched.
* ``reload``  — «♻️ Перезавантажити»: wipe the whole template and import afresh.

Per-date changes (overrides), homework and subject links are never touched by any mode.
Every apply is one journal entry, so it can be undone from «📜 Журнал».
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.db.models import TemplateLesson
from ya32_bot.services import audit, semester
from ya32_bot.services.kv import kv_get, kv_set
from ya32_bot.services.sources.base import SourceLesson, SourceSchedule

SYNC_KEY = "kpi_sync"


class SyncMode(StrEnum):
    APPEND = "append"
    UPDATE = "update"
    RELOAD = "reload"


@dataclass(frozen=True, slots=True)
class FieldChange:
    row_id: int
    lesson: SourceLesson
    fields: tuple[str, ...]


@dataclass
class SyncDiff:
    added: list[SourceLesson] = field(default_factory=list)
    removed: list[TemplateLesson] = field(default_factory=list)  # KPI-sourced rows gone from the source
    changed: list[FieldChange] = field(default_factory=list)
    manual: int = 0  # rows edited by hand (kept by «оновити»)
    total_source: int = 0

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def _key(row: TemplateLesson) -> tuple[int, int, int, str, str]:
    return (row.week, row.weekday, row.slot, row.subject, row.kind)


def _dates(row: TemplateLesson) -> tuple[date, ...]:
    return tuple(sorted(date.fromisoformat(str(d)) for d in row.dates or []))


def _diff_fields(row: TemplateLesson, lesson: SourceLesson) -> tuple[str, ...]:
    out = []
    if (row.teacher or None) != lesson.teacher:
        out.append("teacher")
    if (row.room or None) != lesson.room:
        out.append("room")
    if (row.room_url or None) != lesson.room_url:
        out.append("room_url")
    if _dates(row) != lesson.dates:
        out.append("dates")
    return tuple(out)


def fingerprint(schedule: SourceSchedule) -> str:
    rows = sorted(
        json.dumps(
            [x.week, x.weekday, x.slot, x.subject, x.kind, x.teacher, x.room, x.room_url, [str(d) for d in x.dates]],
            ensure_ascii=False,
        )
        for x in schedule.lessons
    )
    return hashlib.sha256("|".join(rows).encode()).hexdigest()[:16]


async def diff(session: AsyncSession, schedule: SourceSchedule) -> SyncDiff:
    rows = list((await session.scalars(select(TemplateLesson))).all())
    by_key = {_key(r): r for r in rows}
    source_keys = {lesson.key for lesson in schedule.lessons}
    result = SyncDiff(total_source=len(schedule.lessons), manual=sum(1 for r in rows if r.source == "manual"))
    for lesson in schedule.lessons:
        row = by_key.get(lesson.key)
        if row is None:
            result.added.append(lesson)
        elif row.source == "kpi" and (fields := _diff_fields(row, lesson)):
            result.changed.append(FieldChange(row.id, lesson, fields))
    result.removed = [r for r in rows if r.source == "kpi" and _key(r) not in source_keys]
    return result


def _row(lesson: SourceLesson) -> TemplateLesson:
    return TemplateLesson(
        week=lesson.week,
        weekday=lesson.weekday,
        slot=lesson.slot,
        subject=lesson.subject,
        kind=lesson.kind,
        teacher=lesson.teacher,
        room=lesson.room,
        room_url=lesson.room_url,
        dates=[d.isoformat() for d in lesson.dates],
        source="kpi",
    )


@dataclass(frozen=True, slots=True)
class ApplyResult:
    added: int
    changed: int
    removed: int
    journal_id: int | None
    week_set: int | None


async def apply(
    session: AsyncSession,
    schedule: SourceSchedule,
    mode: SyncMode,
    *,
    user_id: int | None,
    today: date,
    now: datetime,
) -> ApplyResult:
    change = audit.Change(f"sync_{mode.value}")
    added = changed = removed = 0

    if mode is SyncMode.RELOAD:
        for row in (await session.scalars(select(TemplateLesson))).all():
            change.deleted(row)
            await session.delete(row)
            removed += 1
        await session.flush()
        for lesson in schedule.lessons:
            row = _row(lesson)
            session.add(row)
            await session.flush()
            change.inserted(row)
            added += 1
    else:
        d = await diff(session, schedule)
        for lesson in d.added:
            row = _row(lesson)
            session.add(row)
            await session.flush()
            change.inserted(row)
            added += 1
        if mode is SyncMode.UPDATE:
            for item in d.changed:
                existing = await session.get(TemplateLesson, item.row_id)
                if existing is None:
                    continue
                before = audit.row_to_dict(existing)
                existing.teacher = item.lesson.teacher
                existing.room = item.lesson.room
                existing.room_url = item.lesson.room_url
                existing.dates = [x.isoformat() for x in item.lesson.dates]
                change.updated(existing, before)
                changed += 1
            for row in d.removed:
                change.deleted(row)
                await session.delete(row)
                removed += 1
        await session.flush()

    week_set = None
    if schedule.current_week in (1, 2):
        await semester.set_anchor(session, today, schedule.current_week)
        week_set = schedule.current_week

    labels = {SyncMode.APPEND: "дозавантаження", SyncMode.UPDATE: "оновлення", SyncMode.RELOAD: "перезавантаження"}
    change.summary = f"КПІ, {labels[mode]}: +{added} ~{changed} −{removed}"
    journal_id = None
    if change.ops:
        journal_id = (await audit.record(session, user_id, change)).id
    await remember(session, schedule, now=now, applied=True)
    return ApplyResult(added, changed, removed, journal_id, week_set)


async def remember(session: AsyncSession, schedule: SourceSchedule, *, now: datetime, applied: bool) -> None:
    state = await kv_get(session, SYNC_KEY)
    state["checked_at"] = now.isoformat()
    state["seen_hash"] = fingerprint(schedule)
    if applied:
        state["applied_at"] = now.isoformat()
        state["applied_hash"] = state["seen_hash"]
    await kv_set(session, SYNC_KEY, state)


async def state(session: AsyncSession) -> dict[str, str]:
    return {k: str(v) for k, v in (await kv_get(session, SYNC_KEY)).items()}
