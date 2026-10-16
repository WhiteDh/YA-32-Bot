"""schedule.kpi.ua — read through its backend, ``api.campus.kpi.ua``.

``GET /schedule/lessons?groupId=<id>``::

    {"groupCode": "...",
     "scheduleFirstWeek":  [{"day": "Пн", "pairs": [<pair>, ...]}, ...],
     "scheduleSecondWeek": [...]}

    <pair> = {"name": "Інвестиційний аналіз", "time": "08:30:00", "tag": "lec|prac|lab",
              "type": "Лек", "lecturer": {"id": "...", "name": "..."} | null,
              "location": {"uri": "...", "title": "17-214"} | null,
              "dates": ["2026-09-14", ...]}   # empty = every such week

``GET /time/current`` → ``{"currentWeek": 1|2, "currentDay": 1..7, "currentLesson": n}``.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx

from ya32_bot.core.slots import slot_for_start
from ya32_bot.services.sources.base import SourceError, SourceLesson, SourceSchedule

logger = logging.getLogger(__name__)

DAY_INDEX = {"пн": 0, "вв": 1, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "нд": 6}
KIND = {"lec": "lec", "prac": "prac", "lab": "lab"}


def parse_lessons(payload: dict[str, Any]) -> tuple[list[SourceLesson], list[str]]:
    """Pure parser, tested on a saved response."""
    lessons: list[SourceLesson] = []
    warnings: list[str] = []
    for week, key in ((1, "scheduleFirstWeek"), (2, "scheduleSecondWeek")):
        for day in payload.get(key) or []:
            weekday = DAY_INDEX.get(str(day.get("day", "")).strip().lower())
            if weekday is None:
                warnings.append(f"невідомий день «{day.get('day')}»")
                continue
            for pair in day.get("pairs") or []:
                slot = slot_for_start(str(pair.get("time", "")))
                name = str(pair.get("name") or "").strip()
                if slot is None or not name:
                    warnings.append(f"пропущено пару «{name or '?'}» о {pair.get('time')}")
                    continue
                lecturer = pair.get("lecturer") or {}
                location = pair.get("location") or {}
                dates: list[date] = []
                for raw in pair.get("dates") or []:
                    try:
                        dates.append(date.fromisoformat(str(raw)[:10]))
                    except ValueError:
                        warnings.append(f"дивна дата «{raw}»")
                lessons.append(
                    SourceLesson(
                        week=week,
                        weekday=weekday,
                        slot=slot,
                        subject=name,
                        kind=KIND.get(str(pair.get("tag") or ""), "other"),
                        teacher=(str(lecturer.get("name") or "").strip() or None),
                        room=(str(location.get("title") or "").strip() or None),
                        room_url=(str(location.get("uri") or "").strip() or None),
                        dates=tuple(sorted(dates)),
                    )
                )
    return lessons, warnings


class KpiCampusSource:
    name = "kpi"
    title = "schedule.kpi.ua"

    def __init__(self, group_id: str, base_url: str = "https://api.campus.kpi.ua", *, timeout: float = 20.0) -> None:
        self.group_id = group_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def page_url(self) -> str:
        return f"https://schedule.kpi.ua/?groupId={self.group_id}"

    async def fetch(self) -> SourceSchedule:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.get("/schedule/lessons", params={"groupId": self.group_id})
                response.raise_for_status()
                payload = response.json()
                current_week: int | None = None
                try:
                    now = await client.get("/time/current")
                    now.raise_for_status()
                    value = now.json().get("currentWeek")
                    current_week = int(value) if value in (1, 2) else None
                except (httpx.HTTPError, ValueError):
                    logger.warning("kpi: could not read the current week", exc_info=True)
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceError(f"КПІ не відповідає: {exc}") from exc
        if not isinstance(payload, dict):
            raise SourceError("КПІ повернув щось незрозуміле")
        lessons, warnings = parse_lessons(payload)
        if not lessons:
            raise SourceError("У відповіді КПІ немає жодної пари — можливо, змінився формат")
        return SourceSchedule(tuple(lessons), current_week, tuple(warnings))
