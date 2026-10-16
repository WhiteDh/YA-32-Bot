"""The contract every schedule source fulfils.

A source returns the two-week template in a neutral shape; :mod:`services.sync`
diffs it against the database and applies it. A new university site = a new class
with ``fetch`` — nothing else in the bot changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SourceLesson:
    week: int  # 1 | 2
    weekday: int  # 0 = Monday
    slot: int
    subject: str
    kind: str = "other"  # lec | prac | lab | other
    teacher: str | None = None
    room: str | None = None
    room_url: str | None = None
    dates: tuple[date, ...] = ()

    @property
    def key(self) -> tuple[int, int, int, str, str]:
        return (self.week, self.weekday, self.slot, self.subject, self.kind)


@dataclass(frozen=True, slots=True)
class SourceSchedule:
    lessons: tuple[SourceLesson, ...]
    current_week: int | None = None  # what the source says this week is, if it knows
    warnings: tuple[str, ...] = field(default_factory=tuple)


class SourceError(RuntimeError):
    """The source could not be read (network, format change)."""


class ScheduleSource(Protocol):
    name: str
    title: str

    async def fetch(self) -> SourceSchedule: ...
