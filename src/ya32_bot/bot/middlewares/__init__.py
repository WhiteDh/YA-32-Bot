"""Outer middlewares: a DB session per update, the current user, light throttling."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from aiogram.types import User as TgUser

from ya32_bot.bot.context import AppContext
from ya32_bot.services import users

logger = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DbSessionMiddleware(BaseMiddleware):
    """One session per update; committed when the handler returns, rolled back on error."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        ctx: AppContext = data["ctx"]
        async with ctx.db.session() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise
            await session.commit()
            return result


class UserMiddleware(BaseMiddleware):
    """Upsert the sender and expose ``user`` and ``prefs`` to handlers."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        # Inline mode is used from other chats by people who may never have opened the bot:
        # registering them would subscribe them to digests the bot cannot even deliver.
        if tg_user is None or tg_user.is_bot or (isinstance(event, Update) and event.inline_query is not None):
            return await handler(event, data)
        ctx: AppContext = data["ctx"]
        user, created = await users.touch(
            data["session"], tg_user.id, tg_user.first_name or "", tg_user.username, ctx.settings.owner_ids
        )
        data["user"] = user
        data["prefs"] = users.prefs_of(user)
        data["user_created"] = created
        return await handler(event, data)


class NavigationResetMiddleware(BaseMiddleware):
    """A command or a bottom-keyboard button abandons any half-finished input.

    Without this, pressing «📅 Сьогодні» while the bot waits for a lesson name would
    save «📅 Сьогодні» as the lesson name.
    """

    def __init__(self, buttons: set[str]) -> None:
        self.buttons = buttons

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, Message) and event.text:
            text = event.text.strip()
            state: FSMContext | None = data.get("state")
            if state is not None and (text.startswith("/") or text in self.buttons) and await state.get_state():
                await state.clear()
        return await handler(event, data)


class ThrottleMiddleware(BaseMiddleware):
    """Drop double-taps: the same button by the same user within ``interval`` seconds.

    Different buttons in quick succession are normal use and always go through.
    """

    def __init__(self, interval: float = 0.6) -> None:
        self.interval = interval
        self._last: dict[tuple[int, str], float] = {}

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, CallbackQuery) and event.from_user is not None:
            key = (event.from_user.id, event.data or "")
            now = time.monotonic()
            if now - self._last.get(key, 0.0) < self.interval:
                await event.answer()
                return None
            self._last[key] = now
            if len(self._last) > 5000:
                self._last.clear()
        return await handler(event, data)
