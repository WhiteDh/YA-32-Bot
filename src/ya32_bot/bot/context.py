"""Process-wide dependencies handed to every handler as ``ctx``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from ya32_bot.config import Settings
from ya32_bot.db.session import Database
from ya32_bot.services.sources import KpiCampusSource, ScheduleSource, SourceSchedule

if TYPE_CHECKING:
    from ya32_bot.bot.notify import Notifier


@dataclass
class AppContext:
    settings: Settings
    db: Database
    source: ScheduleSource
    clock: Callable[[], datetime] | None = None
    notifier: Notifier | None = None
    bot_username: str = ""
    # A fetched-but-not-applied source schedule per admin, so «застосувати» does not refetch.
    pending_sync: dict[int, SourceSchedule] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.settings.tz)

    def now(self) -> datetime:
        """Naive local wall time — the same frame lesson times live in."""
        if self.clock is not None:
            return self.clock()
        return datetime.now(self.tz).replace(tzinfo=None)

    def today(self) -> date:
        return self.now().date()


def build_context(settings: Settings, db: Database) -> AppContext:
    source = KpiCampusSource(settings.kpi_group_id, settings.kpi_api_url)
    return AppContext(settings=settings, db=db, source=source)
