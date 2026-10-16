"""Assembly and entry point: migrate → bot + dispatcher → scheduler → long polling.

Long polling, no webhook: the bot opens no port, so the container needs none.
"""

from __future__ import annotations

import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from ya32_bot.bot import commands, ui
from ya32_bot.bot.context import AppContext, build_context
from ya32_bot.bot.handlers import build_router
from ya32_bot.bot.keyboards.common import REPLY_BUTTONS
from ya32_bot.bot.middlewares import DbSessionMiddleware, NavigationResetMiddleware, ThrottleMiddleware, UserMiddleware
from ya32_bot.bot.notify import Notifier
from ya32_bot.config import Settings, get_settings
from ya32_bot.db.models import Role
from ya32_bot.db.session import Database, migrate
from ya32_bot.logging_setup import setup_logging
from ya32_bot.scheduler import build_scheduler
from ya32_bot.services import users

logger = logging.getLogger(__name__)


def build_dispatcher(ctx: AppContext) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage(), ctx=ctx)
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(UserMiddleware())
    dp.message.outer_middleware(NavigationResetMiddleware(REPLY_BUTTONS))
    throttle = ThrottleMiddleware()
    dp.callback_query.outer_middleware(throttle)
    dp.include_router(build_router())

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        logger.exception("unhandled error in update %s", event.update.update_id, exc_info=event.exception)
        callback = event.update.callback_query
        message = event.update.message
        with contextlib.suppress(Exception):
            if callback is not None:
                await ui.toast(callback, "😵 Щось пішло не так. Спробуй ще раз.", alert=True)
            elif message is not None:
                await message.answer("😵 Щось пішло не так. Спробуй ще раз або /menu.")
        return True

    return dp


async def run(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    if not settings.bot_token.get_secret_value():
        raise SystemExit("BOT_TOKEN is not set — see .env.example")

    await migrate(settings.database_url)
    db = Database(settings.database_url)
    ctx = build_context(settings, db)

    bot = Bot(settings.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=None))
    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError:
        await bot.session.close()
        await db.dispose()
        raise SystemExit("Telegram rejected BOT_TOKEN — issue a new one in @BotFather") from None
    ctx.bot_username = me.username or ""
    ui.RICH.enabled = settings.rich_messages
    notifier = Notifier(bot, ctx)
    ctx.notifier = notifier

    dp = build_dispatcher(ctx)
    async with db.session() as session:
        admins = await users.by_role(session, Role.ADMIN)
    await commands.publish(bot, admins)
    scheduler = build_scheduler(ctx, notifier)
    scheduler.start()
    logger.info("ya32-bot %s started as @%s (tz=%s)", settings.version, ctx.bot_username, settings.tz)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await notifier.close()
        await bot.session.close()
        await db.dispose()
