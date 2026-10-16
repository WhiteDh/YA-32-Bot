"""/start (with invite deep links), menu, help."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from ya32_bot.bot import commands, ui
from ya32_bot.bot.context import AppContext
from ya32_bot.bot.keyboards.callbacks import Nav
from ya32_bot.bot.keyboards.common import btn, kb, reply_menu
from ya32_bot.bot.render.doc import Doc, esc
from ya32_bot.bot.screens import main_menu
from ya32_bot.core.prefs import Prefs
from ya32_bot.db.models import Role, User
from ya32_bot.services import users

router = Router(name="start")

HELP = (
    ("📅 /today · /tomorrow", "розклад на сьогодні / завтра"),
    ("🗓 /week · /nextweek", "цей / наступний тиждень"),
    ("📆 /day 12.10", "будь-який день (або календар у меню)"),
    ("⏱ /now", "яка пара зараз і скільки до кінця"),
    ("📚 /hw", "домашка й дедлайни"),
    ("🔎 /search аналіз", "коли наступні пари предмета (або просто напиши назву)"),
    ("📤 /ics", "розклад файлом у Google / Apple календар"),
    ("⚙️ /settings", "що показувати й коли нагадувати"),
    ("🏠 /menu", "головне меню"),
    ("✖️ /cancel", "скасувати введення"),
)


def keyboard_for(user: User, prefs: Prefs) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    return reply_menu(user.role_enum) if prefs.reply_keyboard else ReplyKeyboardRemove()


@router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject, session: AsyncSession, ctx: AppContext, user: User, prefs: Prefs,
    state: FSMContext, user_created: bool,
) -> None:  # fmt: skip
    await state.clear()
    payload = (command.args or "").strip()
    role: Role | None = None
    if payload.startswith("inv_"):
        role = await users.redeem_invite(session, payload[4:], user)
        if role is None:
            await message.answer("⚠️ Запрошення недійсне або вже використане.")
        else:
            await message.answer(f"🎉 Тепер твоя роль: <b>{esc(user.role_enum.label)}</b>", parse_mode="HTML")

    if message.bot is not None and (role is not None or user_created) and user.role_enum.at_least(Role.ADMIN):
        await commands.sync_user_commands(message.bot, user)
    greet = "Вітаю в боті розкладу <b>ЯА-32</b>! 🎓" if user_created else "З поверненням! 👋"
    await message.answer(
        f"{greet}\nКнопки внизу — для швидкого доступу, а все інше — в меню.",
        parse_mode="HTML",
        reply_markup=keyboard_for(user, prefs),
    )
    doc, markup = main_menu(user, ctx)
    await ui.show(message, doc, markup, rich=prefs.rich)


@router.message(Command("menu"))
async def cmd_menu(message: Message, ctx: AppContext, user: User, prefs: Prefs, state: FSMContext) -> None:
    await state.clear()
    doc, markup = main_menu(user, ctx)
    await ui.show(message, doc, markup, rich=prefs.rich)


@router.callback_query(Nav.filter(F.to == "menu"))
async def cb_menu(callback: CallbackQuery, ctx: AppContext, user: User, prefs: Prefs, state: FSMContext) -> None:
    await state.clear()
    doc, markup = main_menu(user, ctx)
    await ui.show(callback, doc, markup, rich=prefs.rich)


def help_doc(user: User) -> Doc:
    doc = Doc().h("❓ Що я вмію")
    doc.quote(*(f"{cmd} — {esc(what)}" for cmd, what in HELP))
    doc.p(
        "💡 Натисни на номер пари під розкладом — відкриється картка з домашкою й посиланнями.",
        "💡 Пиши <code>@бот</code> у будь-якому чаті, щоб поділитися розкладом.",
    )
    if user.role_enum.at_least(Role.EDITOR):
        doc.p("✍️ Тобі доступне додавання домашки: кнопка «📚 + ДЗ» під днем.")
    if user.role_enum.at_least(Role.ADMIN):
        doc.p("🛠 Адмінка: /admin — редагування днів і шаблону, синхронізація з КПІ, семестр, люди.")
    doc.p("<i>🥚 Тут сховано кілька пасхалок. /secrets — скільки ти вже знайшов.</i>")
    return doc


@router.message(Command("help"))
async def cmd_help(message: Message, user: User, prefs: Prefs) -> None:
    await ui.show(message, help_doc(user), kb([btn("🏠 Меню", Nav(to="menu"))]), rich=prefs.rich)


@router.callback_query(Nav.filter(F.to == "help"))
async def cb_help(callback: CallbackQuery, user: User, prefs: Prefs) -> None:
    await ui.show(callback, help_doc(user), kb([btn("🏠 Меню", Nav(to="menu"))]), rich=prefs.rich)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, user: User, prefs: Prefs) -> None:
    had = await state.get_state()
    await state.clear()
    await message.answer(
        "✖️ Скасовано." if had else "Нічого скасовувати 🙂",
        reply_markup=keyboard_for(user, prefs),
    )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
