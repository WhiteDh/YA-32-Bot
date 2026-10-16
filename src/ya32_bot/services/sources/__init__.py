"""Pluggable schedule sources. Add a class implementing :class:`base.ScheduleSource` and register it here."""

from __future__ import annotations

from ya32_bot.services.sources.base import ScheduleSource, SourceLesson, SourceSchedule
from ya32_bot.services.sources.kpi import KpiCampusSource

__all__ = ["KpiCampusSource", "ScheduleSource", "SourceLesson", "SourceSchedule"]
