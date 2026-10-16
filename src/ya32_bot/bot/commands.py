"""The «/» menu and the bot's profile texts are published from code — never set by hand in @BotFather.

* On every start: the default command list, the description and the short description.
* Per chat for admins: the default list plus the admin commands — on start, and again
  whenever someone's role changes (``sync_user_commands``).
"""

from __future__ import annotations

import contextlib
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from ya32_bot.db.models import Role, User

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="today", description="📅 Сьогодні"),
    BotCommand(command="tomorrow", description="➡️ Завтра"),
    BotCommand(command="week", description="🗓 Цей тиждень"),
    BotCommand(command="nextweek", description="⏭ Наступний тиждень"),
    BotCommand(command="now", description="⏱ Яка пара зараз"),
    BotCommand(command="day", description="📆 Будь-який день: /day 12.10"),
    BotCommand(command="hw", description="📚 Домашка"),
    BotCommand(command="search", description="🔎 Пошук предмета: /search аналіз"),
    BotCommand(command="ics", description="📤 Розклад у Google/Apple календар"),
    BotCommand(command="settings", description="⚙️ Налаштування"),
    BotCommand(command="menu", description="🏠 Меню"),
    BotCommand(command="help", description="❓ Допомога"),
]
ADMIN_COMMANDS = [
    BotCommand(command="admin", description="🛠 Адмінка"),
    BotCommand(command="cancel", description="✖️ Скасувати введення"),
]

DESCRIPTION = (
    "Розклад групи ЯА-32 (КПІ) 🎓\n\n"
    "📅 Пари на сьогодні, завтра й тиждень\n"
    "⏱ Яка пара зараз і скільки до кінця\n"
    "📚 Домашка з дедлайнами\n"
    "🔔 Нагадування — налаштовуються під себе\n\n"
    "Тисни «Почати» 👇"
)
SHORT_DESCRIPTION = "Розклад ЯА-32: пари, домашка, нагадування 🎓"


async def publish(bot: Bot, admins: list[User]) -> None:
    """Default menu + profile texts + per-admin menus. Failures are logged, never fatal."""
    try:
        await bot.set_my_commands(COMMANDS, scope=BotCommandScopeDefault())
        await bot.set_my_description(DESCRIPTION)
        await bot.set_my_short_description(SHORT_DESCRIPTION)
    except TelegramAPIError:
        logger.warning("could not publish the command menu", exc_info=True)
    for admin in admins:
        await sync_user_commands(bot, admin)


async def sync_user_commands(bot: Bot, user: User) -> None:
    """Admins get the admin commands in their chat; everyone else falls back to the default list."""
    scope = BotCommandScopeChat(chat_id=user.id)
    with contextlib.suppress(TelegramAPIError):
        if user.role_enum.at_least(Role.ADMIN):
            await bot.set_my_commands(COMMANDS + ADMIN_COMMANDS, scope=scope)
        else:
            await bot.delete_my_commands(scope=scope)
