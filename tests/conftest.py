"""Shared fixtures: a fresh SQLite database per test, a fixed clock, a fake Telegram."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot.context import AppContext
from ya32_bot.config import Settings
from ya32_bot.db.models import Base
from ya32_bot.db.session import Database
from ya32_bot.services import sync
from ya32_bot.services.sources.base import SourceSchedule
from ya32_bot.services.sources.kpi import parse_lessons

FIXTURES = Path(__file__).parent / "fixtures"
# Monday 5 Oct 2026, 10:40 — inside pair 2; KPI says this is week 2.
NOW = datetime(2026, 10, 5, 10, 40)
OWNER_ID = 1001
STUDENT_ID = 2002


def kpi_payload() -> dict[str, Any]:
    return json.loads((FIXTURES / "kpi_lessons.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def kpi_schedule(current_week: int | None = 2) -> SourceSchedule:
    lessons, warnings = parse_lessons(kpi_payload())
    return SourceSchedule(tuple(lessons), current_week, tuple(warnings))


class FakeSource:
    name = "fake"
    title = "fake source"

    def __init__(self, schedule: SourceSchedule) -> None:
        self.schedule = schedule
        self.calls = 0

    async def fetch(self) -> SourceSchedule:
        self.calls += 1
        return self.schedule


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


@pytest.fixture
async def session(db: Database) -> AsyncIterator[AsyncSession]:
    async with db.session() as s:
        yield s


@pytest.fixture
def clock() -> Clock:
    return Clock(NOW)


@pytest.fixture
def settings() -> Settings:
    return Settings(bot_token="123:TEST", owner_ids=[OWNER_ID], database_url="sqlite+aiosqlite://", kpi_autosync=False)


@pytest.fixture
def ctx(db: Database, clock: Clock, settings: Settings) -> AppContext:
    return AppContext(
        settings=settings, db=db, source=FakeSource(kpi_schedule()), clock=clock, bot_username="ya32_test_bot"
    )


@pytest.fixture
async def seeded(db: Database, ctx: AppContext) -> AppContext:
    """The real KPI schedule of group 3655 imported, semester from 1 Sep to 31 Dec."""
    from ya32_bot.services import semester

    async with db.session() as s:
        await sync.apply(s, kpi_schedule(), sync.SyncMode.APPEND, user_id=None, today=NOW.date(), now=NOW)
        await semester.set_semester_bounds(s, start=date(2026, 9, 1), end=date(2026, 12, 31))
        await s.commit()
    return ctx


# ── Fake Telegram ──────────────────────────────────────────────────────────


class FakeSession(BaseSession):
    """Records every Bot API call and returns a plausible result; can be told to refuse a method."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.refuse: set[str] = set()
        self.forbid: set[str] = set()  # methods answered "bot was blocked by the user"
        self._ids = 100

    async def close(self) -> None:
        return None

    def stream_content(  # pragma: no cover
        self, url: str, headers: dict[str, Any] | None = None, timeout: int = 30, chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes]:  # fmt: skip
        raise NotImplementedError

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 — the signature is aiogram's
    ) -> Any:
        from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

        name = type(method).__name__
        self.calls.append(method)
        if name in self.forbid:
            raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
        if name in self.refuse:
            raise TelegramBadRequest(method=method, message=f"Bad Request: {name} refused in test")
        returning = method.__returning__
        if returning is Message or name in {"SendRichMessage", "EditMessageText"}:
            self._ids += 1
            chat_id = getattr(method, "chat_id", None) or 0
            text = getattr(method, "text", None)
            rich = getattr(method, "rich_message", None)
            return Message(
                message_id=getattr(method, "message_id", None) or self._ids,
                date=datetime(2026, 10, 5),
                chat=Chat(id=int(chat_id), type="private"),
                text=text if text is not None else (rich.html if rich is not None else None),
            )
        if name == "GetMe":
            return TgUser(id=1, is_bot=True, first_name="YA32", username="ya32_test_bot")
        return True

    def of(self, name: str) -> list[TelegramMethod[Any]]:
        return [c for c in self.calls if type(c).__name__ == name]

    def texts(self) -> list[str]:
        out = []
        for call in self.calls:
            text = getattr(call, "text", None)
            rich = getattr(call, "rich_message", None)
            if text:
                out.append(str(text))
            elif rich is not None:
                out.append(str(rich.html))
        return out


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def bot(fake_session: FakeSession) -> Bot:
    return Bot("123:TEST", session=fake_session)
