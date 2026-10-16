"""🥚 Easter eggs. All of them respect «🥚 Пасхалки» in /settings."""

from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import easter
from ya32_bot.bot.context import AppContext
from ya32_bot.core.prefs import Prefs
from ya32_bot.core.texts_uk import human_minutes
from ya32_bot.core.timetable import is_break
from ya32_bot.db.models import User
from ya32_bot.services import schedule

router = Router(name="easter")

FRAME_PAUSE = 1.6
_running: set[asyncio.Task[None]] = set()


@router.message(Command("avatar"))
async def cmd_avatar(message: Message, user: User, prefs: Prefs) -> None:
    await _avatar(message, user, prefs)


@router.message(F.text.func(lambda t: any(x in t.lower() for x in easter.AVATAR_TRIGGERS)))
async def text_avatar(message: Message, user: User, prefs: Prefs) -> None:
    await _avatar(message, user, prefs)


async def _avatar(message: Message, user: User, prefs: Prefs) -> None:
    if not prefs.easter_eggs:
        return
    easter.found(user, "avatar")
    bot = message.bot
    if bot is None:
        return
    sent = await bot.send_message(message.chat.id, easter.AVATAR_FRAMES[0], parse_mode="HTML")
    # Animate after the handler returns, so the update (and its DB session) is not held for ~13 s.
    task = asyncio.create_task(_animate(bot, message.chat.id, sent.message_id))
    _running.add(task)
    task.add_done_callback(_running.discard)


async def _animate(bot: Bot, chat_id: int, message_id: int) -> None:
    for frame in easter.AVATAR_FRAMES[1:]:
        await asyncio.sleep(FRAME_PAUSE)
        with contextlib.suppress(TelegramBadRequest):
            await bot.edit_message_text(frame, chat_id=chat_id, message_id=message_id, parse_mode="HTML")


@router.message(F.text.func(lambda t: any(w in t.lower().split() or w == t.strip() for w in easter.COFFEE_WORDS)))
async def text_coffee(message: Message, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs) -> None:
    if not prefs.easter_eggs:
        return
    now = ctx.now()
    lessons = list((await schedule.day(session, now.date(), today=now.date())).day.active)
    left = is_break(now, lessons)
    easter.found(user, "coffee")
    if left is not None:
        await message.answer(f"☕ Перерва ще {human_minutes(left)} — встигнеш!")
    else:
        await message.answer("☕ Кава — завжди гарна ідея. Хоча зараз і не перерва 😏")


@router.message(Command("42"))
async def cmd_42(message: Message, user: User, prefs: Prefs) -> None:
    if not prefs.easter_eggs:
        return
    easter.found(user, "answer42")
    await message.answer("🌌 Відповідь знайдено. Питання — ні.")


@router.message(Command("secrets"))
async def cmd_secrets(message: Message, user: User, prefs: Prefs) -> None:
    if not prefs.easter_eggs:
        await message.answer("🥚 Пасхалки вимкнено в налаштуваннях.")
        return
    easter.found(user, "secrets")
    found = easter.found_list(user)
    lines = [f"🥚 Знайдено пасхалок: <b>{len(found)} з {len(easter.EGGS)}</b>", ""]
    lines += [f"✅ {easter.EGGS[e]}" for e in found]
    lines += ["❔ ???" for _ in range(len(easter.EGGS) - len(found))]
    await message.answer("\n".join(lines), parse_mode="HTML")
