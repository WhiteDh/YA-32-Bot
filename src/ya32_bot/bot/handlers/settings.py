"""/settings — notification sound and the reminder before a pair; nothing else is personal."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from ya32_bot.bot import ui
from ya32_bot.bot.keyboards.callbacks import Nav, SetCb
from ya32_bot.bot.keyboards.common import BTN_SETTINGS, btn, grid, kb
from ya32_bot.bot.render.doc import Doc
from ya32_bot.core.prefs import NOTIFY_TOGGLES, REMIND_CHOICES, Prefs
from ya32_bot.db.models import User
from ya32_bot.services import users

router = Router(name="settings")

TOGGLE_KEYS = {key for key, _ in NOTIFY_TOGGLES}


def root_screen(prefs: Prefs) -> tuple[Doc, InlineKeyboardMarkup]:
    doc = Doc().h("🔔 Сповіщення")
    remind = f"за {prefs.remind_before} хв" if prefs.remind_before else "вимкнено"
    doc.quote(
        f"Звук: <b>{'увімкнено' if prefs.sound else 'вимкнено'}</b>",
        f"Ранковий розклад: <b>{'за 10 хв до першої пари' if prefs.morning_digest else 'вимкнено'}</b>",
        f"Нагадування про пару: <b>{remind}</b>",
    )
    sound = "🔕 Вимкнути звук" if prefs.sound else "🔔 Увімкнути звук"
    morning = "🌅 Вимкнути ранковий розклад" if prefs.morning_digest else "🌅 Увімкнути ранковий розклад"
    markup = kb(
        [btn(sound, SetCb(a="tog", k="sound"))],
        [btn(morning, SetCb(a="tog", k="morning_digest"))],
        [btn(f"⏰ Нагадування: {remind}", SetCb(a="remind"))],
        [btn("🏠 Меню", Nav(to="menu"))],
    )
    return doc, markup


def remind_screen(prefs: Prefs) -> tuple[Doc, InlineKeyboardMarkup]:
    doc = Doc().h("⏰ Нагадування перед парою").p("За скільки хвилин нагадувати?")
    buttons = [
        btn(
            ("✅ " if prefs.remind_before == m else "") + (f"{m} хв" if m else "Вимкнути"),
            SetCb(a="remindset", v=str(m)),
        )
        for m in REMIND_CHOICES
    ]
    rows = grid(buttons, 3)
    rows.append([btn("← Назад", SetCb(a="open"))])
    return doc, kb(*rows)


@router.message(Command("settings"))
@router.message(F.text == BTN_SETTINGS)
async def msg_settings(message: Message, prefs: Prefs) -> None:
    await ui.show(message, *root_screen(prefs), rich=prefs.rich)


@router.callback_query(Nav.filter(F.to == "settings"))
async def cb_settings(callback: CallbackQuery, prefs: Prefs) -> None:
    await ui.show(callback, *root_screen(prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "open"))
async def cb_open(callback: CallbackQuery, prefs: Prefs) -> None:
    await ui.show(callback, *root_screen(prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "tog"))
async def cb_toggle(callback: CallbackQuery, callback_data: SetCb, user: User, prefs: Prefs) -> None:
    key = callback_data.k
    if key not in TOGGLE_KEYS:
        await ui.toast(callback, "Невідоме налаштування")
        return
    setattr(prefs, key, not getattr(prefs, key))
    users.save_prefs(user, prefs)
    await ui.show(callback, *root_screen(prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "remind"))
async def cb_remind(callback: CallbackQuery, prefs: Prefs) -> None:
    await ui.show(callback, *remind_screen(prefs), rich=prefs.rich)


@router.callback_query(SetCb.filter(F.a == "remindset"))
async def cb_remind_set(callback: CallbackQuery, callback_data: SetCb, user: User, prefs: Prefs) -> None:
    value = int(callback_data.v) if callback_data.v.isdigit() else 0
    prefs.remind_before = value if value in REMIND_CHOICES else 10
    users.save_prefs(user, prefs)
    await ui.toast(callback, f"⏰ За {value} хв до пари" if value else "⏰ Нагадування вимкнено")
    await ui.show(callback, *root_screen(prefs), rich=prefs.rich)
