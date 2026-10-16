"""Weeks, parity and the semester — the bit the old bot hard-coded (``2023-02-05``)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_dates(monday: date, days: int = 7) -> list[date]:
    return [monday + timedelta(days=i) for i in range(days)]


@dataclass(frozen=True, slots=True)
class WeekAnchor:
    """The week starting ``monday`` is study week ``week`` (1 or 2). Every other week follows."""

    monday: date
    week: int

    def week_of(self, day: date) -> int:
        delta_weeks = (monday_of(day) - monday_of(self.monday)).days // 7
        return 1 if (self.week - 1 + delta_weeks) % 2 == 0 else 2


@dataclass(frozen=True, slots=True)
class Holiday:
    start: date
    end: date
    title: str

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end


@dataclass(frozen=True, slots=True)
class Semester:
    start: date | None
    end: date | None
    holidays: tuple[Holiday, ...] = ()

    def holiday_on(self, day: date) -> Holiday | None:
        return next((h for h in self.holidays if h.covers(day)), None)

    def in_session(self, day: date) -> bool:
        if self.start and day < self.start:
            return False
        return not (self.end and day > self.end)

    def days_left(self, today: date) -> int | None:
        return (self.end - today).days if self.end and today <= self.end else None
