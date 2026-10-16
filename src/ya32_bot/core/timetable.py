"""Building a concrete day from the week template plus one-off changes.

Template lessons describe "week 1/2, weekday, pair N". A template lesson may carry
``dates`` (KPI does this for lectures that end mid-semester): then it happens only on
those dates. Overrides are per-date: ``cancel`` a pair, ``replace`` it, or ``add`` one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from itertools import pairwise

from ya32_bot.core.slots import SLOTS, Slot


class LessonKind(StrEnum):
    LECTURE = "lec"
    PRACTICE = "prac"
    LAB = "lab"
    OTHER = "other"

    @property
    def label(self) -> str:
        return KIND_LABELS[self]

    @property
    def emoji(self) -> str:
        return KIND_EMOJI[self]

    @classmethod
    def parse(cls, value: str | None) -> LessonKind:
        try:
            return cls(value or "other")
        except ValueError:
            return cls.OTHER


KIND_LABELS = {
    LessonKind.LECTURE: "Лекція",
    LessonKind.PRACTICE: "Практика",
    LessonKind.LAB: "Лабораторна",
    LessonKind.OTHER: "Заняття",
}
KIND_EMOJI = {
    LessonKind.LECTURE: "📘",
    LessonKind.PRACTICE: "📗",
    LessonKind.LAB: "🧪",
    LessonKind.OTHER: "📙",
}


class OverrideAction(StrEnum):
    CANCEL = "cancel"
    REPLACE = "replace"
    ADD = "add"


@dataclass(frozen=True, slots=True)
class TemplateLesson:
    id: int
    week: int
    weekday: int
    slot: int
    subject: str
    kind: LessonKind = LessonKind.OTHER
    teacher: str | None = None
    room: str | None = None
    room_url: str | None = None
    dates: tuple[date, ...] = ()

    def happens_on(self, day: date, week: int) -> bool:
        if self.week != week or self.weekday != day.weekday():
            return False
        return not self.dates or day in self.dates


@dataclass(frozen=True, slots=True)
class Override:
    id: int
    date: date
    slot: int
    action: OverrideAction
    subject: str | None = None
    kind: LessonKind | None = None
    teacher: str | None = None
    room: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Lesson:
    """One pair on one concrete date, ready to render."""

    date: date
    slot: int
    subject: str
    kind: LessonKind = LessonKind.OTHER
    teacher: str | None = None
    room: str | None = None
    room_url: str | None = None
    note: str | None = None
    template_id: int | None = None
    override_id: int | None = None
    changed: bool = False
    cancelled: bool = False

    @property
    def time(self) -> Slot:
        return SLOTS[self.slot]

    def starts_at(self) -> datetime:
        return datetime.combine(self.date, self.time.start)

    def ends_at(self) -> datetime:
        return datetime.combine(self.date, self.time.end)


@dataclass(frozen=True, slots=True)
class Day:
    date: date
    week: int
    lessons: tuple[Lesson, ...] = ()
    holiday: str | None = None
    out_of_semester: bool = False

    @property
    def active(self) -> tuple[Lesson, ...]:
        return tuple(lesson for lesson in self.lessons if not lesson.cancelled)


def build_day(
    day: date,
    week: int,
    templates: list[TemplateLesson],
    overrides: list[Override],
    *,
    holiday: str | None = None,
    out_of_semester: bool = False,
    keep_cancelled: bool = True,
) -> Day:
    """Merge the template with this date's overrides. Holidays empty the day."""
    if holiday or out_of_semester:
        return Day(day, week, (), holiday=holiday, out_of_semester=out_of_semester)

    by_slot: dict[int, Lesson] = {}
    for tpl in templates:
        if tpl.happens_on(day, week) and tpl.slot not in by_slot:
            by_slot[tpl.slot] = Lesson(
                date=day,
                slot=tpl.slot,
                subject=tpl.subject,
                kind=tpl.kind,
                teacher=tpl.teacher,
                room=tpl.room,
                room_url=tpl.room_url,
                template_id=tpl.id,
            )

    for ov in sorted((o for o in overrides if o.date == day), key=lambda o: o.id):
        current = by_slot.get(ov.slot)
        if ov.action is OverrideAction.CANCEL:
            if current is not None:
                by_slot[ov.slot] = replace(current, cancelled=True, changed=True, override_id=ov.id, note=ov.note)
        elif ov.action is OverrideAction.REPLACE and current is not None:
            by_slot[ov.slot] = replace(
                current,
                subject=ov.subject or current.subject,
                kind=ov.kind or current.kind,
                teacher=ov.teacher if ov.teacher is not None else current.teacher,
                room=ov.room if ov.room is not None else current.room,
                note=ov.note,
                changed=True,
                cancelled=False,
                override_id=ov.id,
            )
        elif ov.action in (OverrideAction.ADD, OverrideAction.REPLACE):
            # REPLACE over an empty slot behaves as ADD — the admin sees the same result.
            by_slot[ov.slot] = Lesson(
                date=day,
                slot=ov.slot,
                subject=ov.subject or "Пара",
                kind=ov.kind or LessonKind.OTHER,
                teacher=ov.teacher,
                room=ov.room,
                note=ov.note,
                override_id=ov.id,
                changed=True,
            )

    lessons = tuple(by_slot[s] for s in sorted(by_slot) if keep_cancelled or not by_slot[s].cancelled)
    return Day(day, week, lessons)


@dataclass(frozen=True, slots=True)
class NowStatus:
    """What is happening at ``moment``: the running pair, the next one, the break."""

    current: Lesson | None = None
    next: Lesson | None = None
    minutes_left: int = 0  # until the current pair ends
    minutes_to_next: int = 0  # until the next pair starts
    progress: float = 0.0  # 0..1 of the current pair
    lessons_left_today: int = 0


def _minutes(delta: timedelta) -> int:
    return max(int(delta.total_seconds() // 60), 0)


def now_status(moment: datetime, upcoming: list[Lesson]) -> NowStatus:
    """``upcoming``: active lessons of today and the following days, any order.

    ``moment`` is naive local wall time (same as lesson datetimes).
    """
    ordered = sorted((lesson for lesson in upcoming if not lesson.cancelled), key=Lesson.starts_at)
    current = next((x for x in ordered if x.starts_at() <= moment < x.ends_at()), None)
    nxt = next((x for x in ordered if x.starts_at() > moment), None)
    left_today = sum(1 for x in ordered if x.date == moment.date() and x.starts_at() > moment)
    status = NowStatus(current=current, next=nxt, lessons_left_today=left_today)
    if current is not None:
        total = (current.ends_at() - current.starts_at()).total_seconds()
        done = (moment - current.starts_at()).total_seconds()
        status = replace(status, minutes_left=_minutes(current.ends_at() - moment), progress=min(done / total, 1.0))
    if nxt is not None:
        status = replace(status, minutes_to_next=_minutes(nxt.starts_at() - moment))
    return status


def is_break(moment: datetime, lessons_today: list[Lesson]) -> int | None:
    """Minutes left of the break between two of today's pairs, or ``None`` outside a break."""
    ordered = sorted((x for x in lessons_today if not x.cancelled), key=Lesson.starts_at)
    for before, after in pairwise(ordered):
        if before.ends_at() <= moment < after.starts_at():
            return _minutes(after.starts_at() - moment)
    return None


def first_start(lessons: list[Lesson]) -> time | None:
    active = [x for x in lessons if not x.cancelled]
    return min((x.time.start for x in active), default=None)
